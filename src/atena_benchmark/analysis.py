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
    tasks_total = summary.get("tasks_total", 0)
    row = {
        "run_id": summary["run_id"],
        "experiment": summary["experiment"],
        "provider": summary["provider"],
        "strategy": summary["strategy"],
        "governance": summary.get("governance", "none"),
        "task_source": summary.get("task_source", "planner"),
        "valid": summary.get("valid", True),
        "cost_usd": summary["total_cost_usd"],
        "tokens": summary["total_tokens"],
        "duration_min": summary["total_duration_ms"] / 60_000,
        "tasks_total": tasks_total,
        "tasks_approved": summary["tasks_completed"],
        "approval_rate": summary["tasks_completed"] / tasks_total if tasks_total else 0.0,
        "repair_cycles": summary["repair_cycles"],
        "model_errors": sum(
            1 for e in summary.get("errors", []) if e["kind"] != "infra"
        ),
        "final_review_approved": bool((summary.get("final_review") or {}).get("approved")),
        "visible_regressions": len(status_changes(visible_baseline, visible_final)["regressions"]),
        "hidden_regressions": len(status_changes(baseline, final)["regressions"]),
        "lines_added": changes.get("additions", 0),
        "lines_removed": changes.get("deletions", 0),
        "files_changed": changes.get("changed_files", 0),
    }
    for check, counts in count_deltas(baseline, final).items():
        for key, (_, after) in counts.items():
            row[f"{check}.{key}"] = after
    evaluation = _load_json(artifacts / "evaluation.json")
    if evaluation:
        for dim in ("requirements", "regressions", "architecture", "security", "simplicity", "tests"):
            row[f"judge.{dim}"] = evaluation[dim]["score"]
        row["judge.blocking"] = sum(
            1 for f in evaluation.get("findings", []) if f["severity"] == "blocking"
        )
    return row


GROUP_KEYS = ("experiment", "provider", "strategy", "governance")


def aggregate(rows: list[dict]) -> list[dict]:
    """Agrupa repetições por (experimento, provider, estratégia, governança).

    Execuções inválidas (falha de infraestrutura) ficam fora das médias e são só contadas.
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
            out[f"{k}.mean"] = statistics.fmean(values)
            out[f"{k}.stdev"] = statistics.stdev(values) if len(values) > 1 else 0.0
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
    ("runs", "Execuções válidas", "{:.0f}"),
    ("invalid_runs", "Inválidas", "{:.0f}"),
    ("cost_usd.mean", "Custo médio (US$)", "{:.4f}"),
    ("tokens.mean", "Tokens médios", "{:,.0f}"),
    ("duration_min.mean", "Tempo médio (min)", "{:.1f}"),
    ("approval_rate.mean", "Taxa de aprovação", "{:.0%}"),
    ("repair_cycles.mean", "Ciclos de correção", "{:.1f}"),
    ("hidden_regressions.mean", "Regressões (oráculo)", "{:.1f}"),
    ("judge.requirements.mean", "Juiz: requisitos", "{:.1f}"),
    ("judge.security.mean", "Juiz: segurança", "{:.1f}"),
    ("judge.simplicity.mean", "Juiz: simplicidade", "{:.1f}"),
]


def to_markdown(groups: list[dict]) -> str:
    if not groups:
        return "Nenhuma execução encontrada.\n"
    headers = ["Experimento", "Provider", "Estratégia", "Governança"]
    columns = [c for c in MARKDOWN_COLUMNS if any(c[0] in g for g in groups)]
    headers += [label for _, label, _ in columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for g in groups:
        cells = [str(g[k]) for k in GROUP_KEYS]
        for key, _, fmt in columns:
            value = g.get(key)
            stdev = g.get(key.replace(".mean", ".stdev"))
            if value is None:
                cells.append("—")
            elif stdev and key.endswith(".mean"):
                cells.append(f"{fmt.format(value)} ± {fmt.format(stdev)}")
            else:
                cells.append(fmt.format(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
