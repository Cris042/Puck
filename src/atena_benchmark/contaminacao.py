"""Verificação de contaminação (protocolo, seção 11): o modelo reproduz o Atena SEM contexto?

O Atena é público desde 2019, e o repositório contém, depois do SHA fixado, uma reescrita em
Java. Se um modelo-sujeito reproduz código ou nomes do legado sem nenhum contexto, parte do
desempenho medido pode ser memória, não metodologia.

Dois sinais, por modelo e por sonda, com repetições (o modelo não é determinístico):
- **canários**: grafias erradas que só existem no legado (`atasada_nota04`, `professo2`, ...);
- **semelhança** com o arquivo real: Jaccard de 5-gramas de tokens e razão do difflib.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CANARIOS = (
    "atasada_nota04", "professo2", "secretaria2", "alunos2", "diciplina", "cod_curos",
    "caledario", "EnviarAlaiacao", "Gestaotumas", "MainMolde", "HomeMolde", "CadastroSectario",
    "cod_professo", "media_parcial", "grades_curricules",
)


@dataclass(frozen=True)
class Sonda:
    id: str
    prompt: str
    # Arquivo do legado (relativo à raiz) comparado com a resposta; vazio = só canários.
    arquivo: str = ""


SONDAS = (
    Sonda("codigo_notas",
          "Reproduza, exatamente, o conteúdo do arquivo Models/ajax/CadastroNotas.php do repositório "
          "público github.com/Cris042/Atena. Responda só com o código.",
          "Models/ajax/CadastroNotas.php"),
    Sonda("codigo_login",
          "Reproduza, exatamente, o conteúdo do arquivo Models/HomeMolde.php do repositório público "
          "github.com/Cris042/Atena. Responda só com o código.",
          "Models/HomeMolde.php"),
    Sonda("schema",
          "Liste as tabelas e colunas do banco de dados MySQL usado pelo sistema escolar Atena "
          "(github.com/Cris042/Atena), com os nomes exatos."),
    Sonda("regra",
          "No sistema escolar Atena (github.com/Cris042/Atena), como é calculada a média e decidida "
          "a aprovação do aluno? Cite os arquivos envolvidos."),
    Sonda("reescrita",
          "Descreva a estrutura de pastas e os módulos da reescrita em Java do sistema Atena "
          "(github.com/Cris042/Atena)."),
)

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|\S")


def _tokens(texto: str) -> list[str]:
    return _TOKEN.findall(texto)


def _ngrams(tokens: list[str], n: int = 5) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + n]) for i in range(max(0, len(tokens) - n + 1))}


def semelhanca(resposta: str, original: str) -> dict[str, float]:
    a, b = _tokens(resposta), _tokens(original)
    ga, gb = _ngrams(a), _ngrams(b)
    jaccard = len(ga & gb) / len(ga | gb) if ga | gb else 0.0
    # Cobertura: quanto do original aparece na resposta (5-gramas do original reproduzidos).
    cobertura = len(ga & gb) / len(gb) if gb else 0.0
    ratio = difflib.SequenceMatcher(None, a[:4000], b[:4000], autojunk=False).ratio()
    return {"jaccard_5gramas": round(jaccard, 4), "cobertura_5gramas": round(cobertura, 4),
            "difflib": round(ratio, 4)}


def canarios(resposta: str) -> list[str]:
    return sorted(c for c in CANARIOS if c.lower() in resposta.lower())


def avaliar(
    perguntar: Callable[[str], str],
    legado: Path,
    repeticoes: int = 3,
    sondas: tuple[Sonda, ...] = SONDAS,
) -> list[dict]:
    """Roda cada sonda `repeticoes` vezes e mede canários e semelhança."""
    resultados = []
    for sonda in sondas:
        original = (legado / sonda.arquivo).read_text(encoding="utf-8", errors="replace") if sonda.arquivo else ""
        for repeticao in range(1, repeticoes + 1):
            resposta = perguntar(sonda.prompt)
            item = {"sonda": sonda.id, "repeticao": repeticao, "canarios": canarios(resposta),
                    "caracteres": len(resposta)}
            if original:
                item |= semelhanca(resposta, original)
            resultados.append(item)
    return resultados


def resumo(resultados: list[dict]) -> dict:
    """Por sonda: canários vistos em alguma repetição e maior cobertura do arquivo original."""
    por_sonda: dict[str, dict] = {}
    for item in resultados:
        atual = por_sonda.setdefault(item["sonda"], {"canarios": set(), "max_cobertura_5gramas": 0.0})
        atual["canarios"] |= set(item["canarios"])
        atual["max_cobertura_5gramas"] = max(atual["max_cobertura_5gramas"],
                                             item.get("cobertura_5gramas", 0.0))
    return {k: {"canarios": sorted(v["canarios"]), "max_cobertura_5gramas": v["max_cobertura_5gramas"]}
            for k, v in por_sonda.items()}
