import json
from pathlib import Path

from atena_benchmark.analysis import aggregate, run_row, status_changes, to_markdown
from atena_benchmark.schemas import CheckResult


def _check(name: str, status: str, required: bool = False, **counts: int) -> dict:
    return CheckResult(
        name=name, command=[], exit_code=0, status=status, required=required,
        duration_ms=0, output="", counts=counts,
    ).model_dump()


def _write_run(
    root: Path, run_id: str, methodology: str, cost: float, valid: bool = True,
    declared: str = "success",
) -> Path:
    artifacts = root / run_id / "artifacts"
    (artifacts / "evaluations").mkdir(parents=True)
    summary = {
        "run_id": run_id, "experiment": "e", "tech": "go", "methodology": methodology,
        "valid": valid, "total_cost_usd": cost, "total_tokens": 100,
        "total_duration_ms": 60_000, "repair_cycles": 1, "errors": [],
        "telemetry_records": 2, "telemetry_parse_failures": 1,
        "baseline_checks": [], "deterministic_checks": [],
        "hidden_baseline_checks": [_check("sg", "failed", total=10), _check("http", "passed")],
        "hidden_final_checks": [_check("sg", "failed", total=4), _check("http", "failed", True)],
        "code_changes": {"additions": 5, "deletions": 1, "changed_files": 2},
    }
    (artifacts / "summary.json").write_text(json.dumps(summary))
    telemetry = [
        {"stage": "implement", "parse_ok": False},
        {"stage": "implement", "parse_ok": True, "report": {"declared_status": declared}},
    ]
    (artifacts / "telemetry.jsonl").write_text("\n".join(json.dumps(t) for t in telemetry))
    evaluation = {d: {"score": 4, "justification": ""} for d in
                  ("requirements", "regressions", "architecture", "security", "simplicity", "tests")}
    evaluation["findings"] = [{"severity": "blocking"}]
    (artifacts / "evaluations" / "claude.json").write_text(json.dumps(evaluation))
    return root / run_id


def test_status_changes_detects_regression_and_fix():
    base = [CheckResult.model_validate(_check("a", "passed")),
            CheckResult.model_validate(_check("b", "unavailable"))]
    final = [CheckResult.model_validate(_check("a", "failed")),
             CheckResult.model_validate(_check("b", "passed"))]
    assert status_changes(base, final) == {"regressions": ["a"], "fixed": ["b"]}


def test_run_row_measures_false_success_parse_failures_and_judges(tmp_path: Path):
    row = run_row(_write_run(tmp_path, "r1", "m1", 1.0))
    assert row["sg.total"] == 4
    assert row["hidden_regressions"] == 1
    assert row["false_success"] == 1  # declarou sucesso, oráculo regrediu
    assert row["telemetry_parse_failure_rate"] == 0.5
    assert row["judge.claude.security"] == 4 and row["judge.claude.blocking"] == 1
    honest = run_row(_write_run(tmp_path, "r2", "m1", 1.0, declared="partial"))
    assert honest["false_success"] == 0


def test_aggregate_reports_median_and_raw_points_excluding_invalid(tmp_path: Path):
    rows = [
        run_row(_write_run(tmp_path, "r1", "m2", 1.0)),
        run_row(_write_run(tmp_path, "r2", "m2", 3.0)),
        run_row(_write_run(tmp_path, "r3", "m2", 99.0, valid=False)),
        run_row(_write_run(tmp_path, "r4", "m1", 5.0)),
    ]
    groups = {g["methodology"]: g for g in aggregate(rows)}
    m2 = groups["m2"]
    assert m2["runs"] == 2 and m2["invalid_runs"] == 1
    assert m2["cost_usd.median"] == 2.0
    assert m2["cost_usd.points"] == "1;3"
    markdown = to_markdown(list(groups.values()))
    assert "2.0000 [1, 3]" in markdown
    assert "claude.security" in markdown
