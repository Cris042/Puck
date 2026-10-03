import json
from pathlib import Path

from atena_benchmark.analysis import aggregate, run_row, status_changes, to_markdown
from atena_benchmark.schemas import CheckResult


def _check(name: str, status: str, **counts: int) -> dict:
    return CheckResult(
        name=name, command=[], exit_code=0, status=status, required=False,
        duration_ms=0, output="", counts=counts,
    ).model_dump()


def _write_run(root: Path, run_id: str, provider: str, cost: float, valid: bool = True) -> Path:
    artifacts = root / run_id / "artifacts"
    artifacts.mkdir(parents=True)
    summary = {
        "run_id": run_id, "experiment": "e", "provider": provider, "strategy": "single",
        "governance": "none", "valid": valid, "total_cost_usd": cost, "total_tokens": 100,
        "total_duration_ms": 60_000, "tasks_total": 2, "tasks_completed": 1, "repair_cycles": 1,
        "errors": [], "final_review": {"approved": True},
        "baseline_checks": [], "deterministic_checks": [],
        "hidden_baseline_checks": [_check("sg", "failed", total=10), _check("lint", "passed")],
        "hidden_final_checks": [_check("sg", "failed", total=4), _check("lint", "failed")],
        "code_changes": {"additions": 5, "deletions": 1, "changed_files": 2},
    }
    (artifacts / "summary.json").write_text(json.dumps(summary))
    return root / run_id


def test_status_changes_detects_regression_and_fix():
    base = [CheckResult.model_validate(_check("a", "passed")),
            CheckResult.model_validate(_check("b", "unavailable"))]
    final = [CheckResult.model_validate(_check("a", "failed")),
             CheckResult.model_validate(_check("b", "passed"))]
    assert status_changes(base, final) == {"regressions": ["a"], "fixed": ["b"]}


def test_aggregate_excludes_invalid_runs(tmp_path: Path):
    rows = [
        run_row(_write_run(tmp_path, "r1", "openai", 1.0)),
        run_row(_write_run(tmp_path, "r2", "openai", 3.0)),
        run_row(_write_run(tmp_path, "r3", "openai", 99.0, valid=False)),
    ]
    assert rows[0]["sg.total"] == 4
    assert rows[0]["hidden_regressions"] == 1
    (group,) = aggregate(rows)
    assert group["runs"] == 2 and group["invalid_runs"] == 1
    assert group["cost_usd.mean"] == 2.0
    assert "2.0000 ± 1.4142" in to_markdown([group])


def test_judge_prompt_is_blind_to_provider_and_strategy(tmp_path: Path):
    from atena_benchmark.evaluation import build_judge_prompt

    final = [CheckResult.model_validate(_check("sg", "failed", total=4))]
    base = [CheckResult.model_validate(_check("sg", "failed", total=10))]
    prompt = build_judge_prompt(
        requirements="REQ", architecture="ARQ", security="SEG", tasks="",
        patch="diff --git a/x b/x\n+novo", visible_baseline=[], visible_final=[],
        hidden_baseline=base, hidden_final=final,
    )
    for leaked in ("anthropic", "openai", "hierarchical", "single", "claude", "gpt"):
        assert leaked not in prompt.lower()
    assert '"total": [\n        10,\n        4\n      ]' in prompt
