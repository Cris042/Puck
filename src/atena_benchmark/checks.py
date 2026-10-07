from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

from .config import ChecksConfig, CheckSpec
from .schemas import CheckResult

MAX_OUTPUT_CHARS = 30_000


def parse_counts(spec: CheckSpec, stdout: str, output: str) -> dict[str, int]:
    if spec.parser == "semgrep_json":
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return {}
        counts = Counter(r["check_id"].rsplit(".", 1)[-1] for r in data.get("results", []))
        counts["total"] = sum(counts.values())
        counts["scan_errors"] = len(data.get("errors", []))
        return dict(counts)
    if spec.parser == "phpunit":
        match = re.search(r"OK \((\d+) tests?, (\d+) assertions?\)", output)
        if match:
            return {"tests": int(match[1]), "assertions": int(match[2]), "failures": 0}
        match = re.search(r"Tests: (\d+), Assertions: (\d+)(.*)", output)
        if not match:
            return {}
        rest = match[3]
        problems = sum(
            int(n) for n in re.findall(r"(?:Errors|Failures): (\d+)", rest)
        )
        return {"tests": int(match[1]), "assertions": int(match[2]), "failures": problems}
    if spec.parser == "puck_metrics":
        # Linhas `PUCK_METRIC <nome> <inteiro>` emitidas pelos comandos do sandbox.
        found = re.findall(r"^PUCK_METRIC (\S+) (-?\d+)$", output, re.M)
        return {name: int(value) for name, value in found}
    if spec.parser == "line_count":
        prefix = spec.line_prefix
        return {"total": sum(1 for line in output.splitlines() if line.startswith(prefix))}
    return {}


class CheckRunner:
    """Executa checks configurados pelo operador.

    Os comandos aceitam os placeholders `{repo_dir}` (workspace da execução), `{config_dir}`
    (diretório do YAML de checks), `{python}` (interpretador do harness, para `-m atena_benchmark`)
    e os valores extras recebidos (ex.: `{tech}`).
    """

    def __init__(
        self,
        repo_dir: Path,
        config: ChecksConfig,
        config_dir: Path | None = None,
        values: dict[str, str] | None = None,
    ):
        self.repo_dir = repo_dir
        self.config = config
        self.config_dir = (config_dir or Path.cwd()).resolve()
        # Placeholders extras do experimento (ex.: {tech}).
        self.values = values or {}

    def names(self) -> list[str]:
        return sorted(self.config.checks)

    def _command(self, spec: CheckSpec) -> list[str]:
        values = {
            "repo_dir": str(self.repo_dir.resolve()),
            "config_dir": str(self.config_dir),
            "python": sys.executable,
            **self.values,
        }
        return [part.format(**values) for part in spec.command]

    def run(self, name: str) -> CheckResult:
        if name not in self.config.checks:
            raise KeyError(f"Check não configurado: {name}")
        spec = self.config.checks[name]
        command = self._command(spec)
        start = perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=self.repo_dir,
                text=True,
                capture_output=True,
                timeout=spec.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = f"Timeout após {spec.timeout_seconds}s.\n{exc.stdout or ''}\n{exc.stderr or ''}"
            return CheckResult(
                name=name,
                command=command,
                exit_code=124,
                status="timeout",
                required=spec.required,
                duration_ms=(perf_counter() - start) * 1000,
                output=output[-MAX_OUTPUT_CHARS:],
            )
        except OSError as exc:
            # Executável do próprio comando ausente (ex.: docker não instalado).
            return CheckResult(
                name=name,
                command=command,
                exit_code=127,
                status="unavailable",
                required=spec.required,
                duration_ms=(perf_counter() - start) * 1000,
                output=str(exc),
            )

        output = (completed.stdout + "\n" + completed.stderr).strip()
        if completed.returncode == 0:
            status = "passed"
        elif completed.returncode in spec.unavailable_exit_codes:
            status = "unavailable"
        else:
            status = "failed"
        return CheckResult(
            name=name,
            command=command,
            exit_code=completed.returncode,
            status=status,
            required=spec.required,
            duration_ms=(perf_counter() - start) * 1000,
            output=output[-MAX_OUTPUT_CHARS:],
            counts=parse_counts(spec, completed.stdout, output),
        )

    def run_all(self) -> list[CheckResult]:
        return [self.run(name) for name in self.names()]
