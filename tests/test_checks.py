import json
import sys
from pathlib import Path

from atena_benchmark.checks import CheckRunner, parse_counts
from atena_benchmark.config import ChecksConfig, CheckSpec


def _runner(tmp_path: Path, **checks: CheckSpec) -> CheckRunner:
    return CheckRunner(tmp_path, ChecksConfig(checks=checks), config_dir=tmp_path / "cfg")


def test_placeholders_are_resolved(tmp_path: Path):
    code = "import sys; print(sys.argv[1]); print(sys.argv[2])"
    spec = CheckSpec(command=[sys.executable, "-c", code, "{repo_dir}", "{config_dir}"])
    result = _runner(tmp_path, echo=spec).run("echo")
    assert result.status == "passed"
    assert str(tmp_path.resolve()) in result.output
    assert str((tmp_path / "cfg").resolve()) in result.output


def test_unavailable_is_decided_by_exit_code_not_by_message(tmp_path: Path):
    missing = CheckSpec(command=[sys.executable, "-c", "raise SystemExit(127)"])
    failing = CheckSpec(command=[sys.executable, "-c", "print('não instalado'); raise SystemExit(2)"])
    runner = _runner(tmp_path, missing=missing, failing=failing)
    assert runner.run("missing").status == "unavailable"
    assert runner.run("failing").status == "failed"


def test_missing_executable_is_unavailable(tmp_path: Path):
    spec = CheckSpec(command=["definitely-not-a-real-binary-xyz"])
    assert _runner(tmp_path, x=spec).run("x").status == "unavailable"


def test_parse_semgrep_counts_by_rule():
    stdout = json.dumps(
        {
            "results": [
                {"check_id": "rules.sql-interpolada"},
                {"check_id": "rules.sql-interpolada"},
                {"check_id": "rules.upload-sem-validacao-de-tipo"},
            ],
            "errors": [],
        }
    )
    counts = parse_counts(CheckSpec(command=["x"], parser="semgrep_json"), stdout, stdout)
    assert counts == {
        "sql-interpolada": 2,
        "upload-sem-validacao-de-tipo": 1,
        "total": 3,
        "scan_errors": 0,
    }


def test_parse_phpunit_success_and_failure():
    spec = CheckSpec(command=["x"], parser="phpunit")
    assert parse_counts(spec, "", "OK (12 tests, 30 assertions)") == {
        "tests": 12,
        "assertions": 30,
        "failures": 0,
    }
    failed = "FAILURES!\nTests: 5, Assertions: 9, Errors: 1, Failures: 2."
    assert parse_counts(spec, "", failed) == {"tests": 5, "assertions": 9, "failures": 3}


def test_parse_line_count():
    spec = CheckSpec(command=["x"], parser="line_count", line_prefix="/app/")
    assert parse_counts(spec, "", "/app/a.php:1:x\nnoise\n/app/b.php:2:y") == {"total": 2}
