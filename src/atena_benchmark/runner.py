from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .agents import AgentSuite
from .checks import CheckRunner
from .config import (
    ChecksConfig,
    Strategy,
    load_checks,
    load_experiment,
    load_models,
    load_pricing,
    load_yaml,
)
from .git_stats import collect_git_stats, mark_untracked_as_intent_to_add
from .graph import build_graph, classify_error
from .metrics import MetricsRecorder
from .models import ModelRegistry
from .prompts import PromptStore
from .reporting import linkedin_report, save_summary
from .schemas import CheckResult, ExperimentSummary, TasksFile
from .settings import settings
from .workspace import prepare_workspace


def _snapshot_inputs(
    *, artifacts_dir: Path, files: dict[str, Path | None], prompts_dir: Path
) -> None:
    snapshot = artifacts_dir / "input-snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for name, src in files.items():
        if src is not None:
            shutil.copy2(src, snapshot / name)
    shutil.copytree(prompts_dir, snapshot / "prompts", dirs_exist_ok=True)

    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout
    (snapshot / "python-environment.txt").write_text(
        f"python={sys.version}\nplatform={platform.platform()}\n\n{freeze}",
        encoding="utf-8",
    )


def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _write_checks(path: Path, results: list[CheckResult]) -> None:
    path.write_text(
        json.dumps([x.model_dump(mode="json") for x in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _git_diff(repo: Path) -> str:
    mark_untracked_as_intent_to_add(repo)
    completed = subprocess.run(
        ["git", "diff", "HEAD", "--", "."], cwd=repo, text=True, capture_output=True, check=False
    )
    return completed.stdout


def run_experiment(
    *,
    experiment_file: Path,
    models_file: Path,
    pricing_file: Path,
    provider: str,
    strategy: Strategy,
    prompts_dir: Path,
    runs_dir: Path | None = None,
) -> tuple[ExperimentSummary, Path]:
    experiment = load_experiment(experiment_file)
    models_config = load_models(models_file)
    pricing = load_pricing(pricing_file)
    checks_path = Path(experiment.checks_file)
    checks = load_checks(checks_path)
    hidden_checks_path = _optional_path(experiment.hidden_checks_file)
    hidden_checks = load_checks(hidden_checks_path) if hidden_checks_path else ChecksConfig()
    tasks_path = _optional_path(experiment.tasks_file)
    fixed_tasks = (
        TasksFile.model_validate(load_yaml(tasks_path)).tasks if tasks_path else []
    )
    governance_path = _optional_path(experiment.governance_file)
    governance = _read(governance_path) if governance_path else ""

    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    workspace = prepare_workspace(
        experiment.repository,
        experiment.base_ref,
        runs_dir or settings.runs_dir,
        run_id,
    )

    requirements_path = Path(experiment.requirements_file)
    architecture_path = Path(experiment.architecture_file)
    security_path = Path(experiment.security_file)
    requirements = _read(requirements_path)
    architecture = _read(architecture_path)
    security = _read(security_path)

    _snapshot_inputs(
        artifacts_dir=workspace.artifacts_dir,
        files={
            "experiment.yaml": experiment_file,
            "models.yaml": models_file,
            "pricing.yaml": pricing_file,
            "requirements.yaml": requirements_path,
            "architecture.md": architecture_path,
            "security.md": security_path,
            "checks.yaml": checks_path,
            "hidden-checks.yaml": hidden_checks_path,
            "tasks.yaml": tasks_path,
            "governance.md": governance_path,
        },
        prompts_dir=prompts_dir,
    )

    model_registry = ModelRegistry(models_config, provider=provider, strategy=strategy)
    check_runner = CheckRunner(workspace.repo_dir, checks, checks_path.parent)
    # Runner separado e nunca entregue às ferramentas dos agentes: é o oráculo da execução.
    hidden_runner = CheckRunner(
        workspace.repo_dir,
        hidden_checks,
        hidden_checks_path.parent if hidden_checks_path else None,
    )
    metrics = MetricsRecorder(workspace.artifacts_dir / "metrics.jsonl", pricing)
    agents = AgentSuite(
        repo_dir=workspace.repo_dir,
        prompts=PromptStore(prompts_dir, governance),
        models=model_registry,
        metrics=metrics,
        checks=check_runner,
        experiment_name=experiment.name,
        provider=provider,
        strategy=strategy,
        run_id=run_id,
        max_agent_steps=experiment.max_agent_steps,
    )
    graph = build_graph(agents, check_runner)

    baseline_checks = check_runner.run_all()
    _write_checks(workspace.artifacts_dir / "baseline-checks.json", baseline_checks)
    hidden_baseline = hidden_runner.run_all()
    _write_checks(workspace.artifacts_dir / "hidden-baseline-checks.json", hidden_baseline)

    started_at = datetime.now(UTC)
    start = time.perf_counter()
    try:
        final_state = graph.invoke(
            {
                "requirements": requirements,
                "architecture": architecture,
                "security": security,
                "fixed_tasks": fixed_tasks,
                "baseline_check_results": baseline_checks,
                "max_repair_cycles": experiment.max_repair_cycles,
                "errors": [],
            },
            config={
                "recursion_limit": 500,
                "run_name": f"{experiment.name}:{provider}:{strategy}",
                "tags": ["atena-benchmark", provider, strategy],
                "metadata": {"run_id": run_id, "experiment": experiment.name},
            },
        )
    except Exception as exc:
        # Falha fora dos nós (bug do harness): preserva métricas e marca a execução inválida.
        final_state = {"errors": [classify_error("graph", exc)]}
    total_duration_ms = (time.perf_counter() - start) * 1000
    finished_at = datetime.now(UTC)

    hidden_final = hidden_runner.run_all()
    _write_checks(workspace.artifacts_dir / "hidden-final-checks.json", hidden_final)

    errors = final_state.get("errors", [])
    all_usages = [u for metric in metrics.invocations for u in metric.usages]
    summary = ExperimentSummary(
        run_id=run_id,
        experiment=experiment.name,
        provider=provider,
        strategy=strategy,
        governance=governance_path.stem if governance_path else "none",
        base_commit=workspace.base_commit,
        task_source="fixed" if fixed_tasks else "planner",
        valid=not any(e.kind == "infra" for e in errors),
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        pricing_date=pricing.pricing_date,
        total_duration_ms=total_duration_ms,
        total_cost_usd=sum(m.estimated_cost_usd for m in metrics.invocations),
        total_input_tokens=sum(u.input_tokens for u in all_usages),
        total_output_tokens=sum(u.output_tokens for u in all_usages),
        total_tokens=sum(u.total_tokens for u in all_usages),
        repair_cycles=final_state.get("total_repair_cycles", 0),
        tasks_total=len(final_state.get("tasks") or fixed_tasks),
        tasks_completed=final_state.get("tasks_completed", 0),
        final_review=final_state.get("final_review"),
        task_outcomes=final_state.get("task_outcomes", []),
        errors=errors,
        unpriced_models=metrics.unpriced_models(),
        baseline_checks=baseline_checks,
        deterministic_checks=final_state.get("check_results", []),
        hidden_baseline_checks=hidden_baseline,
        hidden_final_checks=hidden_final,
        invocations=metrics.invocations,
    )

    git_stats = collect_git_stats(workspace.repo_dir)
    save_summary(summary, workspace.artifacts_dir / "summary.json", git_stats)
    (workspace.artifacts_dir / "linkedin-report.md").write_text(
        linkedin_report(summary, git_stats), encoding="utf-8"
    )
    (workspace.artifacts_dir / "changes.patch").write_text(
        _git_diff(workspace.repo_dir), encoding="utf-8"
    )

    return summary, workspace.run_dir
