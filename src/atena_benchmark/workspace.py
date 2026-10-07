from __future__ import annotations

import os
import re
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


_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class ScaffoldChangedError(RuntimeError):
    """O esqueleto não é mais o congelado no experimento: mudança de tratamento."""


def resolve_sha(repository: str, ref: str) -> str:
    """SHA efetivo de `ref`. Caminho local é resolvido no clone; remoto, via `git ls-remote`.

    SHA completo é devolvido como está (ls-remote não resolve SHA). Falha vira texto explícito,
    nunca um valor que pareça SHA.
    """
    path = Path(repository).expanduser()
    if (path / ".git").exists():
        completed = subprocess.run(
            ["git", "rev-parse", f"{ref}^{{commit}}"], cwd=path, text=True,
            capture_output=True, check=False,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
    if _FULL_SHA.match(ref):
        return ref
    completed = subprocess.run(
        ["git", "ls-remote", repository, ref], text=True, capture_output=True, check=False
    )
    first = completed.stdout.split()
    return first[0] if first else f"unresolved:{ref}"


def export_tree(source: str, ref: str, dest: Path) -> str:
    """Cópia somente-leitura de `source@ref`, sem `.git`: nem histórico nem commits futuros."""
    _run(["git", "clone", "-q", source, str(dest)])
    _run(["git", "checkout", "-q", "--detach", ref], cwd=dest)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=dest)
    shutil.rmtree(dest / ".git")
    for path in sorted(dest.rglob("*"), reverse=True):
        if path.is_file():
            path.chmod(0o444)
    return sha


# Autor e data fixos: o mesmo conteúdo gera sempre o mesmo SHA, então o esqueleto copiado de um
# diretório (ex.: scaffolds/<tech>) tem SHA reprodutível e registrável no summary.json.
_FIXED_COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "Puck",
    "GIT_AUTHOR_EMAIL": "puck@local",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_NAME": "Puck",
    "GIT_COMMITTER_EMAIL": "puck@local",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


def commit_snapshot(repo_dir: Path) -> str:
    """`git init` + commit determinístico do conteúdo atual (respeitando o .gitignore)."""
    env = {**os.environ, **_FIXED_COMMIT_ENV}
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "--no-gpg-sign", "-m", "esqueleto"],
    ):
        subprocess.run(command, cwd=repo_dir, check=True, capture_output=True, text=True, env=env)
    return _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)


def prepare_workspace(source: str, base_ref: str, runs_dir: Path, run_id: str) -> Workspace:
    run_dir = (runs_dir / run_id).resolve()
    repo_dir = run_dir / "repo"
    artifacts_dir = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=False)
    artifacts_dir.mkdir(parents=True)

    source_path = Path(source).expanduser()
    if source_path.exists() and not (source_path / ".git").exists():
        shutil.copytree(source_path, repo_dir)
        sha = commit_snapshot(repo_dir)
        # `base_ref` com SHA completo congela o esqueleto: conteúdo diferente recusa a execução.
        if _FULL_SHA.match(base_ref) and sha != base_ref:
            raise ScaffoldChangedError(
                f"{source}: conteúdo gera {sha}, experimento congelado em {base_ref}"
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
