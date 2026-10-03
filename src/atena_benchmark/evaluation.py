"""Avaliação independente pós-execução.

O revisor dentro do workflow é o modelo `strong` do próprio provider avaliado: serve para o
ciclo de correção, mas não para comparar providers, porque cada um estaria corrigindo a própria
prova. Aqui um juiz fixo (o mesmo para todas as execuções) avalia o patch sem saber qual
provider, estratégia ou modelo o produziu.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain.chat_models import init_chat_model

from .analysis import count_deltas, status_changes
from .config import JudgeSpec, PricingConfig
from .metrics import MetricsRecorder
from .schemas import CheckResult, EvaluationResult

MAX_PATCH_CHARS = 150_000

JUDGE_SYSTEM_PROMPT = """Você é um avaliador independente de um experimento de engenharia de software.
Avalie SOMENTE o patch e as evidências fornecidas, contra os requisitos, a arquitetura-alvo e os
requisitos de segurança. Você não sabe qual modelo ou estratégia produziu o patch; não tente
adivinhar e não considere estilo de escrita como critério.

Escala por dimensão (1 a 5):
1 = piora clara ou ausência total; 2 = insuficiente; 3 = aceitável com lacunas relevantes;
4 = bom, lacunas menores; 5 = excelente, sem lacunas identificáveis.

Dimensões:
- requirements: requisitos atendidos pelo que está no patch (não pelo que foi prometido).
- regressions: risco de quebra de comportamento existente; use os checks ocultos como evidência.
- architecture: aderência às restrições arquiteturais declaradas.
- security: vulnerabilidades corrigidas × introduzidas; use as contagens do Semgrep como evidência.
- simplicity: ausência de overengineering; solução proporcional ao problema.
- tests: testes que realmente exercitam o comportamento alterado.

Achado `blocking` é somente: comportamento errado/ausente, regressão, vazamento de dado ou segredo,
falso verde (teste que passa sem provar nada), perda de dado. O resto é `non_blocking`.
Cite evidência (arquivo/trecho do patch ou nome do check) em cada achado. Não invente evidência.
Se o patch estiver truncado, diga isso no resumo e avalie apenas o que foi visto."""


def build_judge_prompt(
    *,
    requirements: str,
    architecture: str,
    security: str,
    tasks: str,
    patch: str,
    visible_baseline: list[CheckResult],
    visible_final: list[CheckResult],
    hidden_baseline: list[CheckResult],
    hidden_final: list[CheckResult],
) -> str:
    truncated = len(patch) > MAX_PATCH_CHARS
    patch_text = patch[:MAX_PATCH_CHARS] + ("\n... PATCH TRUNCADO ..." if truncated else "")

    def checks_view(baseline: list[CheckResult], final: list[CheckResult]) -> str:
        before = {c.name: c.status for c in baseline}
        return json.dumps(
            {
                "status": {c.name: {"baseline": before.get(c.name), "final": c.status} for c in final},
                "mudancas": status_changes(baseline, final),
                "contagens_baseline_final": count_deltas(baseline, final),
            },
            ensure_ascii=False,
            indent=2,
        )

    return f"""REQUISITOS:
{requirements}

ARQUITETURA-ALVO:
{architecture}

SEGURANÇA:
{security}

TAREFAS DO EXPERIMENTO:
{tasks or 'Definidas pelo próprio workflow (não fixas).'}

CHECKS VISÍVEIS AOS AGENTES (baseline × final):
{checks_view(visible_baseline, visible_final)}

CHECKS OCULTOS / ORÁCULO (baseline × final; os agentes não tiveram acesso):
{checks_view(hidden_baseline, hidden_final)}

PATCH ({len(patch):,} caracteres{', truncado' if truncated else ''}):
```diff
{patch_text}
```
"""


def evaluate_run(run_dir: Path, judge: JudgeSpec, pricing: PricingConfig) -> EvaluationResult:
    artifacts = run_dir / "artifacts" if (run_dir / "artifacts").is_dir() else run_dir
    snapshot = artifacts / "input-snapshot"
    summary = json.loads((artifacts / "summary.json").read_text(encoding="utf-8"))

    def snap(name: str) -> str:
        path = snapshot / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def checks(key: str) -> list[CheckResult]:
        return [CheckResult.model_validate(c) for c in summary.get(key, [])]

    prompt = build_judge_prompt(
        requirements=snap("requirements.yaml"),
        architecture=snap("architecture.md"),
        security=snap("security.md"),
        tasks=snap("tasks.yaml"),
        patch=(artifacts / "changes.patch").read_text(encoding="utf-8"),
        visible_baseline=checks("baseline_checks"),
        visible_final=checks("deterministic_checks"),
        hidden_baseline=checks("hidden_baseline_checks"),
        hidden_final=checks("hidden_final_checks"),
    )

    kwargs = {"timeout": judge.timeout, "max_retries": judge.max_retries, **judge.extra}
    if judge.reasoning_effort is not None:
        kwargs["reasoning_effort"] = judge.reasoning_effort
    if judge.temperature is not None:
        kwargs["temperature"] = judge.temperature
    if judge.max_tokens is not None:
        kwargs["max_tokens"] = judge.max_tokens
    model = init_chat_model(model=judge.model, model_provider=judge.provider, **kwargs)
    structured = model.with_structured_output(EvaluationResult)

    metrics = MetricsRecorder(artifacts / "evaluation-metrics.jsonl", pricing)
    result = metrics.measured_invoke(
        role="judge",
        tier="judge",
        run_name="atena-benchmark:judge",
        tags=["atena-benchmark", "judge"],
        # Metadata identifica a execução para rastreio, mas nada disso entra no prompt.
        metadata={"run_id": summary["run_id"], "judge_model": judge.model},
        invoke=structured.invoke,
        payload=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        configured_model=judge.model,
    )
    payload = result.model_dump(mode="json")
    payload["judge"] = {"provider": judge.provider, "model": judge.model}
    (artifacts / "evaluation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
