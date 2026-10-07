from __future__ import annotations

import json
from pathlib import Path

from .analysis import count_deltas, status_changes
from .schemas import ExperimentSummary


def save_summary(summary: ExperimentSummary, path: Path, git_stats: dict) -> None:
    payload = summary.model_dump(mode="json")
    payload["code_changes"] = git_stats
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_report(summary: ExperimentSummary, git_stats: dict) -> str:
    """Resumo legível de UMA execução. Comparação entre células é feita por `compare`."""
    review = summary.final_review
    hidden_changes = status_changes(summary.hidden_baseline_checks, summary.hidden_final_checks)
    hidden_counts = count_deltas(summary.hidden_baseline_checks, summary.hidden_final_checks)
    hidden_rows = "".join(
        f"| {check}: {key} | {before} → {after} |\n"
        for check, counts in hidden_counts.items()
        for key, (before, after) in counts.items()
        if key != "scan_errors"
    )
    validity = "válida" if summary.valid else "**inválida** (falha de infraestrutura; repetir)"
    shas = "".join(f"| {name} | `{sha[:12]}` |\n" for name, sha in summary.source_shas.items())
    if summary.methodology == "m2":
        verdict = "aprovado" if review and review.approved else "com pendências"
        gates = f"| Tarefas aprovadas pelo revisor | {summary.tasks_completed}/{summary.tasks_total} |\n"
        gates += f"| Ciclos de reparo | {summary.repair_cycles} |\n"
        gates += f"| Revisão final | {verdict} |\n"
    else:
        gates = "| Gates | não se aplica (M1) |\n"
    return f"""# Execução {summary.run_id}

Experimento **{summary.experiment}** · tech **{summary.tech}** · metodologia **{summary.methodology}** · {validity}

## Origem

| Repositório | SHA |
|---|---|
{shas}
## Custo e esforço

| Indicador | Valor |
|---|---:|
| Custo de execução (US$) | {summary.total_cost_usd:.4f} |
| Tokens de execução (entrada / saída / cache lido) | {summary.total_input_tokens:,} / {summary.total_output_tokens:,} / {summary.total_cache_read_tokens:,} |
| Tempo total (min) | {summary.total_duration_ms / 60_000:.1f} |
| Custo de telemetria (US$, fora do custo de execução) | {summary.telemetry_cost_usd:.4f} |
| Registros de telemetria / falhas de parse | {summary.telemetry_records} / {summary.telemetry_parse_failures} |
{gates}| Erros (modelo + infra) | {len(summary.errors)} |
| Arquivos alterados / linhas + / − | {git_stats.get('changed_files', 0)} / {git_stats.get('additions', 0)} / {git_stats.get('deletions', 0)} |

## Oráculo oculto (esqueleto → final)

| Contador | Valor |
|---|---:|
{hidden_rows or '| — | sem checks ocultos com parser |' + chr(10)}
Regressões no oráculo: {len(hidden_changes['regressions'])}.

Uma execução isolada não sustenta conclusão: o protocolo compara medianas por célula.
"""
