from __future__ import annotations

import json
from pathlib import Path

from .analysis import count_deltas, status_changes
from .schemas import ExperimentSummary


def save_summary(summary: ExperimentSummary, path: Path, git_stats: dict) -> None:
    payload = summary.model_dump(mode="json")
    payload["code_changes"] = git_stats
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def linkedin_report(summary: ExperimentSummary, git_stats: dict) -> str:
    review = summary.final_review
    verdict = "Aprovado na revisão final" if review and review.approved else "Com pendências"
    checks_passed = sum(1 for c in summary.deterministic_checks if c.status == "passed")
    checks_failed = sum(1 for c in summary.deterministic_checks if c.status == "failed")
    new_check_failures = len(
        status_changes(summary.baseline_checks, summary.deterministic_checks)["regressions"]
    )
    hidden_changes = status_changes(summary.hidden_baseline_checks, summary.hidden_final_checks)
    hidden_counts = count_deltas(summary.hidden_baseline_checks, summary.hidden_final_checks)
    hidden_rows = "".join(
        f"| {check}: {key} | {before} → {after} |\n"
        for check, counts in hidden_counts.items()
        for key, (before, after) in counts.items()
        if key not in {"scan_errors"}
    )
    validity = (
        "Válida"
        if summary.valid
        else "**Inválida** (falha de infraestrutura; repita antes de comparar)"
    )
    architecture_violations = len(review.architecture_violations) if review else 0
    security_findings = len(review.security_findings) if review else 0
    overengineering_findings = len(review.overengineering_findings) if review else 0
    requirement_gaps = len(review.requirements_gaps) if review else 0
    return f"""# Benchmark de LLMs aplicado à Engenharia de Software

## Contexto
Experimento: **{summary.experiment}**  
Provider: **{summary.provider}**  
Estratégia: **{summary.strategy}**  
Governança: **{summary.governance}**  
Commit base: `{summary.base_commit[:12]}`  
Execução: {validity}

O objetivo é avaliar custo e eficiência sem tratar o resultado como um ranking universal de modelos.

## Resultados resumidos

| Indicador | Resultado |
|---|---:|
| Custo estimado de API | US$ {summary.total_cost_usd:.4f} |
| Tokens de entrada | {summary.total_input_tokens:,} |
| Tokens de saída | {summary.total_output_tokens:,} |
| Tokens totais | {summary.total_tokens:,} |
| Tarefas ({summary.task_source}) | {summary.tasks_total} |
| Tarefas aprovadas | {summary.tasks_completed} |
| Ciclos de correção | {summary.repair_cycles} |
| Lacunas de requisitos | {requirement_gaps} |
| Violações arquiteturais | {architecture_violations} |
| Achados de segurança | {security_findings} |
| Indícios de overengineering | {overengineering_findings} |
| Checks aprovados | {checks_passed} |
| Checks com falha | {checks_failed} |
| Novas falhas vs. baseline | {new_check_failures} |
| Regressões no oráculo oculto | {len(hidden_changes['regressions'])} |
| Erros de agente/infra | {len(summary.errors)} |
| Arquivos alterados | {git_stats.get('changed_files', 0)} |
| Linhas adicionadas | {git_stats.get('additions', 0)} |
| Linhas removidas | {git_stats.get('deletions', 0)} |
| Revisão final | {verdict} |

## Oráculo oculto (baseline → final)

| Contador | Valor |
|---|---:|
{hidden_rows or '| — | sem checks ocultos com parser |' + chr(10)}
Contagens de regras estáticas são sinais, não prova de segurança ou de qualidade.

## Critérios observados
- aderência aos requisitos;
- aderência à arquitetura;
- segurança;
- regressões e retrabalho;
- complexidade/overengineering;
- consumo de tokens, tempo e custo.

## Leitura dos resultados
Este benchmark representa **um cenário específico**. Software é um sistema vivo e cada domínio possui prioridades, riscos e restrições próprias. Um modelo ou estratégia que se sair melhor aqui não é automaticamente superior em todos os projetos.

Um sistema financeiro ou outro sistema crítico pode priorizar consistência, segurança, auditabilidade e tolerância a falhas. Uma rede social ou outro sistema menos crítico pode aceitar trade-offs diferentes em troca de velocidade, experimentação e custo.

O objetivo, portanto, não é descobrir uma LLM vencedora, mas entender **quanto de capacidade, custo e complexidade cada problema realmente exige** e quais trade-offs aparecem em cada estratégia.
"""
