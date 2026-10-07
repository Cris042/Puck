from __future__ import annotations

import subprocess
from pathlib import Path


def _run(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    return completed.stdout.strip()


def mark_untracked_as_intent_to_add(repo: Path) -> None:
    """Faz `git diff HEAD` enxergar arquivos novos sem preparar conteúdo para commit."""
    _run(repo, "add", "--intent-to-add", "--all", "--", ".")


def snapshot_tree(repo: Path) -> str:
    """SHA de uma árvore com o estado atual do workspace, sem criar commit."""
    _run(repo, "add", "-A", "--", ".")
    return _run(repo, "write-tree")


def diff_since(repo: Path, tree: str) -> str:
    """Diff do que mudou no workspace desde `snapshot_tree` (uma etapa de agente)."""
    after = snapshot_tree(repo)
    return _run(repo, "diff", tree, after)


def collect_git_stats(repo: Path) -> dict:
    mark_untracked_as_intent_to_add(repo)
    numstat = _run(repo, "diff", "HEAD", "--numstat", "--", ".")
    name_status = _run(repo, "diff", "HEAD", "--name-status", "--", ".")

    additions = 0
    deletions = 0
    binary_files = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        if parts[0] == "-":
            binary_files += 1
            continue
        additions += int(parts[0])
        deletions += int(parts[1])

    statuses = [line.split("\t", 1)[0][:1] for line in name_status.splitlines() if line]
    return {
        "changed_files": len(statuses),
        "new_files": statuses.count("A"),
        "deleted_files": statuses.count("D"),
        "modified_files": statuses.count("M"),
        "binary_files": binary_files,
        "additions": additions,
        "deletions": deletions,
    }
