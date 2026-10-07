from __future__ import annotations

import csv
import io
import json
import statistics
from collections import defaultdict
from pathlib import Path

from .schemas import CheckResult

FAILING = {"failed", "timeout", "error"}


def status_changes(
    baseline: list[CheckResult], final: list[CheckResult]
) -> dict[str, list[str]]:
    """Checks que quebraram (regressão) ou passaram a funcionar em relação ao baseline."""
    before = {c.name: c.status for c in baseline}
    regressions, fixed = [], []
    for check in final:
        old = before.get(check.name)
        if check.status in FAILING and old not in FAILING:
            regressions.append(check.name)
        elif check.status == "passed" and old in FAILING | {"unavailable"}:
            fixed.append(check.name)
    return {"regressions": regressions, "fixed": fixed}


def count_deltas(
    baseline: list[CheckResult], final: list[CheckResult]
) -> dict[str, dict[str, tuple[int, int]]]:
    """{check: {contador: (baseline, final)}} para checks com parser."""
    before = {c.name: c.counts for c in baseline}
    deltas: dict[str, dict[str, tuple[int, int]]] = {}
    for check in final:
        old = before.get(check.name, {})
        keys = sorted(set(old) | set(check.counts))
        if keys:
            deltas[check.name] = {k: (old.get(k, 0), check.counts.get(k, 0)) for k in keys}
    return deltas


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


JUDGE_DIMENSIONS = ("requirements", "regressions", "architecture", "security", "simplicity", "tests")


def false_success(telemetry: list[dict], hidden_regressions: int, hidden_final: list[CheckResult]) -> int:
    """1 se o executor declarou sucesso na última etapa e o oráculo mostra o contrário."""
    declared = [
        r["report"]["declared_status"] for r in telemetry if r.get("parse_ok") and r.get("report")
    ]
    if not declared or declared[-1] != "success":
        return 0
    oracle_failed = hidden_regressions > 0 or any(
        c.required and c.status in FAILING for c in hidden_final
    )
    return int(oracle_failed)


def run_row(run_dir: Path) -> dict | None:
    """Uma linha plana por execução, com métricas comparáveis entre execuções."""
    artifacts = run_dir / "artifacts" if (run_dir / "artifacts").is_dir() else run_dir
    summary = _load_json(artifacts / "summary.json")
    if summary is None:
        return None
    baseline = [CheckResult.model_validate(c) for c in summary.get("hidden_baseline_checks", [])]
    final = [CheckResult.model_validate(c) for c in summary.get("hidden_final_checks", [])]
    visible_baseline = [CheckResult.model_validate(c) for c in summary.get("baseline_checks", [])]
    visible_final = [
        CheckResult.model_validate(c) for c in summary.get("deterministic_checks", [])
    ]
    changes = summary.get("code_changes", {})
    telemetry = _load_jsonl(artifacts / "telemetry.jsonl")
    hidden_regressions = len(status_changes(baseline, final)["regressions"])
    records = summary.get("telemetry_records", 0)
    row = {
        "run_id": summary["run_id"],
        "experiment": summary["experiment"],
        "tech": summary["tech"],
        "methodology": summary["methodology"],
        "valid": summary.get("valid", True),
        "started_at": summary.get("started_at", ""),
        "cost_usd": summary["total_cost_usd"],
        "tokens": summary["total_tokens"],
        "input_tokens": summary.get("total_input_tokens", 0),
        "output_tokens": summary.get("total_output_tokens", 0),
        "cache_read_tokens": summary.get("total_cache_read_tokens", 0),
        "duration_min": summary["total_duration_ms"] / 60_000,
        "telemetry_cost_usd": summary.get("telemetry_cost_usd", 0.0),
        "telemetry_parse_failure_rate": (
            summary.get("telemetry_parse_failures", 0) / records if records else 0.0
        ),
        "false_success": false_success(telemetry, hidden_regressions, final),
        "repair_cycles": summary.get("repair_cycles", 0),
        "model_errors": sum(1 for e in summary.get("errors", []) if e["kind"] != "infra"),
        "visible_regressions": len(status_changes(visible_baseline, visible_final)["regressions"]),
        "hidden_regressions": hidden_regressions,
        "lines_added": changes.get("additions", 0),
        "lines_removed": changes.get("deletions", 0),
        "files_changed": changes.get("changed_files", 0),
    }
    for check, counts in count_deltas(baseline, final).items():
        for key, (_, after) in counts.items():
            row[f"{check}.{key}"] = after
    for path in sorted((artifacts / "evaluations").glob("*.json")):
        evaluation = _load_json(path)
        if not evaluation:
            continue
        judge = path.stem
        for dim in JUDGE_DIMENSIONS:
            row[f"judge.{judge}.{dim}"] = evaluation[dim]["score"]
        row[f"judge.{judge}.blocking"] = sum(
            1 for f in evaluation.get("findings", []) if f["severity"] == "blocking"
        )
    return row


GROUP_KEYS = ("experiment", "tech", "methodology")


def _fmt_number(value: float) -> str:
    return f"{value:.4g}"


def aggregate(rows: list[dict]) -> list[dict]:
    """Agrupa repetições por (experimento, tech, metodologia): mediana + pontos brutos.

    Com n pequeno por célula, média ± desvio sugere uma precisão que não existe; o protocolo pede
    mediana e todos os pontos. Execuções inválidas ficam fora e são só contadas.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in GROUP_KEYS)].append(row)

    result = []
    for key, items in sorted(groups.items()):
        valid = [r for r in items if r["valid"]]
        out = dict(zip(GROUP_KEYS, key, strict=True))
        out["runs"] = len(valid)
        out["invalid_runs"] = len(items) - len(valid)
        numeric = sorted(
            {
                k
                for r in valid
                for k, v in r.items()
                if isinstance(v, int | float) and not isinstance(v, bool) and k not in GROUP_KEYS
            }
        )
        for k in numeric:
            values = [float(r[k]) for r in valid if k in r]
            if not values:
                continue
            out[f"{k}.median"] = statistics.median(values)
            out[f"{k}.min"] = min(values)
            out[f"{k}.max"] = max(values)
            out[f"{k}.points"] = ";".join(_fmt_number(v) for v in values)
        result.append(out)
    return result


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k not in GROUP_KEYS, k))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


MARKDOWN_COLUMNS = [
    ("cost_usd", "Custo (US$)", "{:.4f}"),
    ("tokens", "Tokens", "{:,.0f}"),
    ("duration_min", "Tempo (min)", "{:.1f}"),
    ("hidden_regressions", "Regressões (oráculo)", "{:.0f}"),
    ("false_success", "Falso sucesso", "{:.0f}"),
    ("repair_cycles", "Ciclos de reparo", "{:.0f}"),
    ("telemetry_parse_failure_rate", "Falha de parse (telemetria)", "{:.0%}"),
]


def to_markdown(groups: list[dict]) -> str:
    """Mediana com os pontos brutos entre colchetes, por célula."""
    if not groups:
        return "Nenhuma execução encontrada.\n"
    judge_columns = sorted(
        {k.removesuffix(".median") for g in groups for k in g if k.startswith("judge.")
         and k.endswith(".median")}
    )
    columns = [c for c in MARKDOWN_COLUMNS if any(f"{c[0]}.median" in g for g in groups)]
    columns += [(k, k.removeprefix("judge."), "{:.1f}") for k in judge_columns]
    headers = ["Experimento", "Tech", "Metodologia", "Válidas", "Inválidas"]
    headers += [label for _, label, _ in columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for g in groups:
        cells = [str(g[k]) for k in GROUP_KEYS] + [str(g["runs"]), str(g["invalid_runs"])]
        for key, _, fmt in columns:
            median = g.get(f"{key}.median")
            if median is None:
                cells.append("—")
                continue
            points = g[f"{key}.points"].replace(";", ", ")
            cells.append(f"{fmt.format(median)} [{points}]")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
