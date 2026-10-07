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
    M2_ROLES,
    ChecksConfig,
    ExperimentConfig,
    Methodology,
    ModelsConfig,
    load_checks,
    load_experiment,
    load_models,
    load_pricing,
)
from .git_stats import collect_git_stats, mark_untracked_as_intent_to_add
from .graph import build_graph, classify_error
from .metrics import MetricsRecorder
from .models import ModelRegistry
from .prompts import PromptStore, render
from .reporting import run_report, save_summary
from .schemas import CheckResult, ExperimentSummary
from .settings import settings
from .workspace import export_tree, prepare_workspace, resolve_sha


def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def snapshot_inputs(
    *, artifacts_dir: Path, files: dict[str, Path | None], prompts_dir: Path
) -> None:
    """Cópia de tudo que define o tratamento, para a execução ser reconstruível sem o repo."""
    snapshot = artifacts_dir / "input-snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    for name, src in files.items():
        if src is not None:
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    shutil.copytree(prompts_dir, snapshot / "prompts", dirs_exist_ok=True)
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"], text=True, capture_output=True, check=False
    ).stdout
    (snapshot / "python-environment.txt").write_text(
        f"python={sys.version}\nplatform={platform.platform()}\n\n{freeze}", encoding="utf-8"
    )


def build_brief(experiment: ExperimentConfig, requirements: str) -> str:
    """Entrada idêntica para M1 e M2: requisitos, base técnica e tarefas renderizadas."""
    values = {"tech": experiment.tech, "requisitos": requirements}
    values |= {key: _read(path) for key, path in experiment.context_files.items()}
    tasks = "\n\n---\n\n".join(render(_read(path), values) for path in experiment.task_files)
    annexes = "".join(
        f"\n## {Path(path).name}\n\n```{Path(path).suffix.lstrip('.')}\n{_read(path).strip()}\n```\n"
        for path in experiment.spec_files
    )
    return f"""# REQUISITOS

{requirements}

# BASE TÉCNICA OBRIGATÓRIA

{_read(experiment.base_tecnica_file)}

# ANEXOS OBRIGATÓRIOS
{annexes or chr(10) + "Nenhum."}

# TAREFAS

{tasks or "Implementar os requisitos acima."}
"""


def generation_params(models: ModelsConfig, methodology: Methodology) -> dict[str, dict]:
    roles = ("agent",) if methodology == "m1" else M2_ROLES
    params = {role: models.spec_for(methodology, role).generation_params() for role in roles}
    params["telemetry"] = models.telemetry.generation_params()
    return params


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


def _snapshot_files(
    experiment_file: Path, models_file: Path, pricing_file: Path, experiment: ExperimentConfig
) -> dict[str, Path | None]:
    files: dict[str, Path | None] = {
        "experiment.yaml": experiment_file,
        "models.yaml": models_file,
        "pricing.yaml": pricing_file,
        "requirements": Path(experiment.requirements_file),
        "base-tecnica.md": Path(experiment.base_tecnica_file),
        "checks.yaml": Path(experiment.checks_file),
        "hidden-checks.yaml": Path(experiment.hidden_checks_file)
        if experiment.hidden_checks_file
        else None,
    }
    for path in experiment.spec_files:
        files[f"spec/{Path(path).name}"] = Path(path)
    for path in experiment.task_files:
        files[f"tasks/{Path(path).name}"] = Path(path)
    for key, path in experiment.context_files.items():
        files[f"context/{key}{Path(path).suffix}"] = Path(path)
    for path in experiment.m2_governance_files:
        files[f"governance-m2/{Path(path).name}"] = Path(path)
    return files


def run_experiment(
    *,
    experiment_file: Path,
    models_file: Path,
    pricing_file: Path,
    methodology: Methodology,
    prompts_dir: Path,
    runs_dir: Path | None = None,
) -> tuple[ExperimentSummary, Path]:
    experiment = load_experiment(experiment_file)
    models_config = load_models(models_file)
    pricing = load_pricing(pricing_file)
    checks_path = Path(experiment.checks_file)
    checks = load_checks(checks_path)
    hidden_checks_path = (
        Path(experiment.hidden_checks_file) if experiment.hidden_checks_file else None
    )
    hidden_checks = load_checks(hidden_checks_path) if hidden_checks_path else ChecksConfig()
    governance = (
        "\n\n".join(_read(p) for p in experiment.m2_governance_files) if methodology == "m2" else ""
    )

    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    workspace = prepare_workspace(
        experiment.scaffold.repository,
        experiment.scaffold.ref,
        runs_dir or settings.runs_dir,
        run_id,
    )
    legacy_dir = workspace.run_dir / "legado"
    source_shas = {
        "scaffold": workspace.base_commit,
        "legacy": export_tree(experiment.legacy.repository, experiment.legacy.ref, legacy_dir),
        **{name: resolve_sha(ref.repository, ref.ref) for name, ref in experiment.references.items()},
    }
    source_shas["puck"] = resolve_sha(str(Path(__file__).resolve().parents[2]), "HEAD")

    requirements = _read(experiment.requirements_file)
    brief = build_brief(experiment, requirements)
    snapshot_inputs(
        artifacts_dir=workspace.artifacts_dir,
        files=_snapshot_files(experiment_file, models_file, pricing_file, experiment),
        prompts_dir=prompts_dir,
    )
    (workspace.artifacts_dir / "input-snapshot" / "brief.md").write_text(brief, encoding="utf-8")

    model_registry = ModelRegistry(models_config, methodology)
    placeholders = {"tech": experiment.tech}
    check_runner = CheckRunner(workspace.repo_dir, checks, checks_path.parent, placeholders)
    # Runner separado e nunca entregue às ferramentas dos agentes: é o oráculo da execução.
    hidden_runner = CheckRunner(
        workspace.repo_dir,
        hidden_checks,
        hidden_checks_path.parent if hidden_checks_path else None,
        placeholders,
    )
    metrics = MetricsRecorder(workspace.artifacts_dir / "metrics.jsonl", pricing)
    agents = AgentSuite(
        repo_dir=workspace.repo_dir,
        legacy_dir=legacy_dir,
        prompts=PromptStore(prompts_dir, governance),
        models=model_registry,
        metrics=metrics,
        checks=check_runner,
        experiment_name=experiment.name,
        tech=experiment.tech,
        run_id=run_id,
        max_agent_steps=experiment.max_agent_steps,
        m1_max_agent_steps=experiment.m1_max_agent_steps,
    )
    graph = build_graph(methodology, agents, check_runner)

    baseline_checks = check_runner.run_all()
    _write_checks(workspace.artifacts_dir / "baseline-checks.json", baseline_checks)
    hidden_baseline = hidden_runner.run_all()
    _write_checks(workspace.artifacts_dir / "hidden-baseline-checks.json", hidden_baseline)

    started_at = datetime.now(UTC)
    start = time.perf_counter()
    try:
        final_state = graph.invoke(
            {
                "brief": brief,
                "requirements": requirements,
                "documents": experiment.m2_documents,
                "baseline_check_results": baseline_checks,
                "max_repair_cycles": experiment.max_repair_cycles,
                "telemetry": [],
                "errors": [],
            },
            config={
                "recursion_limit": 500,
                "run_name": f"{experiment.name}:{experiment.tech}:{methodology}",
                "tags": ["puck", experiment.tech, methodology],
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

    telemetry = final_state.get("telemetry", [])
    with (workspace.artifacts_dir / "telemetry.jsonl").open("w", encoding="utf-8") as f:
        for record in telemetry:
            f.write(record.model_dump_json() + "\n")

    execution = metrics.of_kind("execution")
    exec_usages = [u for m in execution for u in m.usages]
    telemetry_calls = metrics.of_kind("telemetry")
    errors = final_state.get("errors", [])
    summary = ExperimentSummary(
        run_id=run_id,
        experiment=experiment.name,
        tech=experiment.tech,
        methodology=methodology,
        source_shas=source_shas,
        generation_params=generation_params(models_config, methodology),
        valid=not any(e.kind == "infra" for e in errors),
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        pricing_date=pricing.pricing_date,
        total_duration_ms=total_duration_ms,
        total_cost_usd=sum(m.estimated_cost_usd for m in execution),
        total_input_tokens=sum(u.input_tokens for u in exec_usages),
        total_output_tokens=sum(u.output_tokens for u in exec_usages),
        total_cache_read_tokens=sum(u.cache_read_tokens for u in exec_usages),
        total_tokens=sum(u.total_tokens for u in exec_usages),
        telemetry_cost_usd=sum(m.estimated_cost_usd for m in telemetry_calls),
        telemetry_tokens=sum(u.total_tokens for m in telemetry_calls for u in m.usages),
        telemetry_records=len(telemetry),
        telemetry_parse_failures=sum(1 for r in telemetry if not r.parse_ok),
        repair_cycles=final_state.get("total_repair_cycles", 0),
        tasks_total=len(final_state.get("tasks") or []),
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
    (workspace.artifacts_dir / "report.md").write_text(
        run_report(summary, git_stats), encoding="utf-8"
    )
    (workspace.artifacts_dir / "changes.patch").write_text(
        _git_diff(workspace.repo_dir), encoding="utf-8"
    )
    return summary, workspace.run_dir
