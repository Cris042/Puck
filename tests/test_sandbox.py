import os
import shutil
from pathlib import Path

import pytest

from atena_benchmark.checks import parse_counts
from atena_benchmark.config import CheckSpec, load_experiment
from atena_benchmark.sandbox import coverage_metrics, run_make_target, run_with_app
from atena_benchmark.workspace import ScaffoldChangedError, commit_snapshot, prepare_workspace

ROOT = Path(__file__).resolve().parents[1]
DOCKER = pytest.mark.skipif(
    os.environ.get("PUCK_DOCKER_TESTS") != "1",
    reason="testes com Docker: PUCK_DOCKER_TESTS=1 (e `atena-bench sandbox build-images`)",
)

COBERTURA = """<?xml version="1.0"?>
<coverage><packages><package><classes>
  <class filename="app/Modulos/Boletim/Service/Media.php">
    <methods><method name="m"><lines><line number="1" hits="1"/><line number="2" hits="0"/></lines></method></methods>
    <lines><line number="1" hits="1"/><line number="2" hits="0"/></lines>
  </class>
  <class filename="app/Modulos/Boletim/Http/Controlador.php">
    <lines><line number="1" hits="1"/><line number="2" hits="1"/></lines>
  </class>
</classes></package></packages></coverage>"""


def test_coverage_counts_class_lines_once_and_core_layers_apart():
    metrics = coverage_metrics(COBERTURA)
    assert metrics == {
        "coverage_lines": 4,
        "coverage_permille": 750,
        "coverage_core_permille": 500,
    }


def test_puck_metrics_parser_reads_only_metric_lines():
    spec = CheckSpec(command=["x"], parser="puck_metrics")
    output = "ruído\nPUCK_METRIC coverage_permille 812\nPUCK_METRIC p95_ms -1\nPUCK_METRIC x y\n"
    assert parse_counts(spec, output, output) == {"coverage_permille": 812, "p95_ms": -1}


@pytest.mark.parametrize("tech", ["laravel", "go"])
def test_scaffold_sha_is_deterministic_and_frozen_in_experiment(tech: str, tmp_path: Path):
    copies = []
    for name in ("a", "b"):
        shutil.copytree(ROOT / "scaffolds" / tech, tmp_path / name)
        copies.append(commit_snapshot(tmp_path / name))
    assert copies[0] == copies[1]
    experiment = load_experiment(ROOT / f"spec/atena/experiment-{tech}.yaml")
    assert experiment.scaffold.ref == copies[0], "esqueleto mudou: atualize o SHA congelado"


def test_changed_scaffold_refuses_to_start(tmp_path: Path):
    source = tmp_path / "esqueleto"
    shutil.copytree(ROOT / "scaffolds/go", source)
    (source / "extra.txt").write_text("mudança")
    frozen = load_experiment(ROOT / "spec/atena/experiment-go.yaml").scaffold.ref
    with pytest.raises(ScaffoldChangedError):
        prepare_workspace(str(source), frozen, tmp_path / "runs", "r1")


@DOCKER
@pytest.mark.parametrize("tech", ["laravel", "go"])
def test_scaffold_passes_its_checks_in_sandbox(tech: str):
    for target in ("lint", "arch", "test"):
        assert run_make_target(tech, target, ROOT / "scaffolds" / tech) == 0, target


@DOCKER
@pytest.mark.parametrize("tech", ["laravel", "go"])
def test_scaffold_app_boots_and_answers_health(tech: str):
    command = ["sh", "-c", "curl -sf $TARGET_URL/saude"]
    assert run_with_app(tech, ROOT / "scaffolds" / tech, "curlimages/curl:8.16.0", command) == 0
