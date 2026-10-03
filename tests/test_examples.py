from pathlib import Path

import pytest

from atena_benchmark.config import load_checks, load_experiment, load_models, load_yaml
from atena_benchmark.schemas import TasksFile

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path", sorted((ROOT / "examples").rglob("experiment*.yaml")))
def test_example_experiments_reference_existing_files(path: Path):
    experiment = load_experiment(path)
    for field in (
        "requirements_file", "architecture_file", "security_file", "checks_file",
        "hidden_checks_file", "tasks_file", "governance_file",
    ):
        value = getattr(experiment, field)
        if value:
            assert (ROOT / value).is_file(), f"{path.name}: {field} → {value}"


def test_example_configs_are_valid():
    load_models(ROOT / "config/models.example.yaml")
    for checks in (ROOT / "config").glob("*checks*.yaml"):
        load_checks(checks)
    tasks = TasksFile.model_validate(load_yaml(ROOT / "examples/atena/tasks.yaml")).tasks
    assert len({t.id for t in tasks}) == len(tasks)
