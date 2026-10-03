from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    pass


def safe_repo_path(root: Path, relative: str) -> Path:
    if not relative or relative.strip() in {".", "./"}:
        return root.resolve()
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise UnsafePathError(f"Path fora do workspace: {relative}")
    if ".git" in candidate.parts:
        raise UnsafePathError("Acesso direto a .git não é permitido")
    return candidate
