"""Avaliação independente pós-execução.

O revisor da M2 participa do tratamento e não serve para comparar metodologias. Aqui juízes fixos
(os mesmos para a campanha inteira, um Claude calibrado e um de outro provider) avaliam o patch sem
saber qual metodologia o produziu. Documentos de processo (`docs/`) são retirados do patch: ADR,
PRD, HLD e FDD existem só na M2 e revelariam a configuração.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .analysis import count_deltas, status_changes
from .config import JudgeSpec, PricingConfig
from .metrics import MetricsRecorder
from .models import build_chat_model
from .prompts import PromptStore
from .schemas import CheckResult, EvaluationResult

MAX_PATCH_CHARS = 150_000
HIDDEN_FROM_JUDGE = ("docs/",)
_FILE_HEADER = re.compile(r"^diff --git a/(\S+) ", re.M)


def filter_patch(patch: str, excluded_prefixes: tuple[str, ...] = HIDDEN_FROM_JUDGE) -> str:
    """Remove do patch os arquivos cujo caminho começa com um dos prefixos."""
    starts = [m.start() for m in _FILE_HEADER.finditer(patch)]
    if not starts:
        return patch
    blocks = [patch[a:b] for a, b in zip(starts, [*starts[1:], len(patch)], strict=True)]
    kept = [b for b in blocks if not _FILE_HEADER.match(b)[1].startswith(excluded_prefixes)]
    return patch[: starts[0]] + "".join(kept)


def build_judge_prompt(
    *,
    brief: str,
    patch: str,
    visible_baseline: list[CheckResult],
    visible_final: list[CheckResult],
    hidden_baseline: list[CheckResult],
    hidden_final: list[CheckResult],
) -> str:
    patch = filter_patch(patch)
    truncated = len(patch) > MAX_PATCH_CHARS
    patch_text = patch[:MAX_PATCH_CHARS] + ("\n... PATCH TRUNCADO ..." if truncated else "")

    def checks_view(baseline: list[CheckResult], final: list[CheckResult]) -> str:
        before = {c.name: c.status for c in baseline}
        return json.dumps(
            {
                "status": {c.name: {"inicial": before.get(c.name), "final": c.status} for c in final},
                "mudancas": status_changes(baseline, final),
                "contagens_inicial_final": count_deltas(baseline, final),
            },
            ensure_ascii=False,
            indent=2,
        )

    return f"""ESPECIFICAÇÃO ENTREGUE AO PROJETO:
{brief}

CHECKS DO PROJETO (esqueleto inicial × final):
{checks_view(visible_baseline, visible_final)}

ORÁCULO OCULTO (esqueleto inicial × final; o projeto não teve acesso):
{checks_view(hidden_baseline, hidden_final)}

PATCH ({len(patch):,} caracteres{', truncado' if truncated else ''}; documentos em docs/ omitidos):
```diff
{patch_text}
```
"""


def evaluate_run(
    run_dir: Path, judge: JudgeSpec, pricing: PricingConfig, prompts_dir: Path
) -> EvaluationResult:
    artifacts = run_dir / "artifacts" if (run_dir / "artifacts").is_dir() else run_dir
    summary = json.loads((artifacts / "summary.json").read_text(encoding="utf-8"))

    def checks(key: str) -> list[CheckResult]:
        return [CheckResult.model_validate(c) for c in summary.get(key, [])]

    prompt = build_judge_prompt(
        brief=(artifacts / "input-snapshot" / "brief.md").read_text(encoding="utf-8"),
        patch=(artifacts / "changes.patch").read_text(encoding="utf-8"),
        visible_baseline=checks("baseline_checks"),
        visible_final=checks("deterministic_checks"),
        hidden_baseline=checks("hidden_baseline_checks"),
        hidden_final=checks("hidden_final_checks"),
    )
    model = build_chat_model(judge, judge.provider)
    method = "json_schema" if judge.provider == "anthropic" else "function_calling"
    structured = model.with_structured_output(EvaluationResult, method=method)

    output_dir = artifacts / "evaluations"
    output_dir.mkdir(exist_ok=True)
    metrics = MetricsRecorder(output_dir / f"{judge.name}-metrics.jsonl", pricing)
    result = metrics.measured_invoke(
        role="judge",
        kind="judge",
        run_name=f"puck:judge:{judge.name}",
        tags=["puck", "judge", judge.name],
        # Metadata identifica a execução para rastreio, mas nada disso entra no prompt.
        metadata={"run_id": summary["run_id"], "judge_model": judge.model},
        invoke=structured.invoke,
        payload=[
            {"role": "system", "content": PromptStore(prompts_dir).load("juiz")},
            {"role": "user", "content": prompt},
        ],
        configured_model=judge.model,
    )
    payload = result.model_dump(mode="json")
    payload["judge"] = {"name": judge.name, "provider": judge.provider, "model": judge.model}
    (output_dir / f"{judge.name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
