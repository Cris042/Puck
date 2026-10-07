"""Execução seca ponta a ponta: repositórios git locais e agentes falsos no lugar das LLMs."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from atena_benchmark import runner
from atena_benchmark.git_stats import diff_since, snapshot_tree
from atena_benchmark.schemas import StepReport, TelemetryRecord, TelemetryReport

ROOT = Path(__file__).resolve().parents[1]


def _git_repo(path: Path, files: dict[str, str]) -> str:
    path.mkdir(parents=True)
    for name, content in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(content)
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], cwd=path, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


class FakeSuite:
    """Escreve um arquivo como o agente faria e mede a etapa com o diff real do workspace."""

    instances: list["FakeSuite"] = []

    def __init__(self, *, repo_dir, legacy_dir, prompts, **kwargs):
        self.repo_dir = repo_dir
        self.legacy_dir = legacy_dir
        self.system_prompt = prompts.system_prompt("m1", "agent")
        self.briefs: list[str] = []
        FakeSuite.instances.append(self)

    def checkpoint(self):
        return snapshot_tree(self.repo_dir)

    def agent(self, brief):
        self.briefs.append(brief)
        (self.repo_dir / "internal" / "boletim").mkdir(parents=True)
        (self.repo_dir / "internal" / "boletim" / "media.go").write_text("package boletim\n")
        return StepReport(status="completed", final_message="STATUS: success")

    def telemetry(self, *, stage, task_id, attempt, needs_rework, since_tree, step, requirements):
        diff = diff_since(self.repo_dir, since_tree)
        return TelemetryRecord(
            stage=stage, task_id=task_id, attempt=attempt, needs_rework=needs_rework,
            parse_ok="media.go" in diff,
            report=TelemetryReport(declared_status="success"),
        )


@pytest.fixture
def experiment(tmp_path: Path) -> Path:
    scaffold_sha = _git_repo(tmp_path / "scaffold", {"go.mod": "module escola\n"})
    legacy_sha = _git_repo(tmp_path / "atena", {"Models/HomeMolde.php": "<?php // login\n"})
    _git_repo(tmp_path / "minerva", {"README.md": "minerva\n"})
    (tmp_path / "checks.yaml").write_text("checks: {}\n")
    config = {
        "name": "seco",
        "tech": "go",
        "scaffold": {"repository": str(tmp_path / "scaffold"), "ref": scaffold_sha},
        "legacy": {"repository": str(tmp_path / "atena"), "ref": legacy_sha},
        "references": {"minerva": {"repository": str(tmp_path / "minerva"), "ref": "HEAD"}},
        "requirements_file": str(ROOT / "spec/atena/requisitos.md"),
        "base_tecnica_file": str(ROOT / "spec/base-tecnica/BASE_TECNICA.md"),
        "task_files": [str(ROOT / "prompts/tarefas/refatoracao-banco.md")],
        "context_files": {"mer_der": str(ROOT / "docs/legado/MER_DER.md")},
        "checks_file": str(tmp_path / "checks.yaml"),
        "m2_governance_files": [str(ROOT / "governance/m2/minerva.md")],
    }
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def test_dry_run_produces_every_artifact(tmp_path: Path, experiment: Path, monkeypatch):
    monkeypatch.setattr(runner, "AgentSuite", FakeSuite)
    summary, run_dir = runner.run_experiment(
        experiment_file=experiment,
        models_file=ROOT / "config/models.example.yaml",
        pricing_file=ROOT / "config/pricing.example.yaml",
        methodology="m1",
        prompts_dir=ROOT / "prompts",
        runs_dir=tmp_path / "runs",
    )
    artifacts = run_dir / "artifacts"
    for name in ("summary.json", "metrics.jsonl", "telemetry.jsonl", "changes.patch", "report.md",
                 "baseline-checks.json", "hidden-baseline-checks.json",
                 "hidden-final-checks.json"):
        assert (artifacts / name).exists(), name
    snapshot = artifacts / "input-snapshot"
    for name in ("experiment.yaml", "models.yaml", "pricing.yaml", "requirements",
                 "base-tecnica.md", "brief.md", "tasks/refatoracao-banco.md",
                 "context/mer_der.md", "prompts/m1/agente.md"):
        assert (snapshot / name).exists(), name

    # Tarefa renderizada com o MER/DER e a tech; nenhum placeholder sobrando.
    brief = (snapshot / "brief.md").read_text()
    assert "Atena legado — MER e DER" in brief and "{mer_der}" not in brief
    assert "reescrita da aplicação em go" in brief

    assert summary.methodology == "m1" and summary.tech == "go"
    assert set(summary.source_shas) == {"scaffold", "legacy", "minerva", "puck"}
    assert summary.generation_params["agent"] == {
        "model": "claude-opus-5-5", "effort": "medium", "max_tokens": 16000,
    }
    assert summary.telemetry_records == 1 and summary.telemetry_parse_failures == 0
    assert "internal/boletim/media.go" in (artifacts / "changes.patch").read_text()

    # Legado exportado sem .git, e a M1 não recebe governança.
    fake = FakeSuite.instances[-1]
    assert (fake.legacy_dir / "Models/HomeMolde.php").exists()
    assert not (fake.legacy_dir / ".git").exists()
    assert "Minerva" not in fake.system_prompt
    saved = json.loads((artifacts / "summary.json").read_text())
    assert saved["code_changes"]["new_files"] == 1
