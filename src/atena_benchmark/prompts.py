from __future__ import annotations

import re
from pathlib import Path

_COMMENT = re.compile(r"<!--.*?-->\s*", re.S)


def strip_comments(text: str) -> str:
    """Comentários HTML documentam o prompt para humanos; não vão para o modelo."""
    return _COMMENT.sub("", text).strip()


def render(template: str, values: dict[str, str]) -> str:
    """Substitui só `{chave}` conhecidas; chaves de código (`{}` em JSON, PHP, Go) ficam intactas."""
    text = strip_comments(template)
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


class PromptStore:
    """Prompts congelados por metodologia.

    M1: `m1/agente.md`, sem governança. M2: `m2/<papel>.md` + arquivos de governança da M2.
    Instrumentos (telemetria, juiz) ficam na raiz e são iguais para as duas metodologias.
    """

    def __init__(self, root: Path, governance: str = ""):
        self.root = root
        self.governance = governance.strip()

    def load(self, name: str) -> str:
        return strip_comments((self.root / f"{name}.md").read_text(encoding="utf-8"))

    def system_prompt(self, methodology: str, role: str) -> str:
        if methodology == "m1":
            return self.load("m1/agente")
        parts = [self.load(f"m2/{role}")]
        if self.governance:
            parts.append(self.governance)
        return "\n\n---\n\n".join(parts)
