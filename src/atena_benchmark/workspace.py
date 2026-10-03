from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    run_dir: Path
    repo_dir: Path
    artifacts_dir: Path
    base_commit: str


def _run(command: list[str], cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def prepare_workspace(source: str, base_ref: str, runs_dir: Path, run_id: str) -> Workspace:
    run_dir = (runs_dir / run_id).resolve()
    repo_dir = run_dir / "repo"
    artifacts_dir = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=False)
    artifacts_dir.mkdir(parents=True)

    source_path = Path(source).expanduser()
    if source_path.exists() and not (source_path / ".git").exists():
        shutil.copytree(source_path, repo_dir)
        _run(["git", "init", "-q"], cwd=repo_dir)
        _run(["git", "add", "-A"], cwd=repo_dir)
        _run(
            [
                "git", "-c", "user.email=benchmark@local", "-c", "user.name=LLM Benchmark",
                "commit", "-q", "-m", "benchmark baseline",
            ],
            cwd=repo_dir,
        )
    else:
        # Clone completo + checkout aceita branch, tag ou SHA (`--branch` não aceita SHA).
        # Repositórios privados devem ser clonados antes e informados como caminho local.
        origin = str(source_path.resolve()) if source_path.exists() else source
        _run(["git", "clone", "-q", origin, str(repo_dir)])
        _run(["git", "checkout", "-q", "--detach", base_ref], cwd=repo_dir)
        # Sem remote: o histórico futuro do projeto não deve vazar para o workspace.
        _run(["git", "remote", "remove", "origin"], cwd=repo_dir)

    base_commit = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
    return Workspace(
        run_dir=run_dir, repo_dir=repo_dir, artifacts_dir=artifacts_dir, base_commit=base_commit
    )
