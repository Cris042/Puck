from __future__ import annotations

from pathlib import Path


class PromptStore:
    def __init__(self, root: Path, governance: str = ""):
        self.root = root
        self.governance = governance.strip()

    def load(self, name: str) -> str:
        path = self.root / f"{name}.md"
        return path.read_text(encoding="utf-8").strip()

    def system_prompt(self, role: str) -> str:
        parts = [self.load("common")]
        if self.governance:
            parts.append(self.governance)
        parts.append(self.load(role))
        return "\n\n---\n\n".join(parts)
