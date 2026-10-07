from pathlib import Path

import pytest
from pydantic import ValidationError

from atena_benchmark.config import (
    M1Models,
    M2Models,
    ModelsConfig,
    ModelSpec,
    PriceSpec,
    PricingConfig,
    load_checks,
    load_experiment,
    load_models,
    pricing_problems,
)

ROOT = Path(__file__).resolve().parents[1]


def _models(agent: str, worker: str, telemetry: str) -> ModelsConfig:
    m2 = {role: ModelSpec(model=worker) for role in M2Models.model_fields}
    return ModelsConfig(
        m1=M1Models(agent=ModelSpec(model=agent)),
        m2=M2Models(**m2),
        telemetry=ModelSpec(model=telemetry),
    )


def test_pricing_problems_flags_missing_zero_and_placeholder_date():
    pricing = PricingConfig(
        pricing_date="YYYY-MM-DD",
        models={"a": PriceSpec(input_per_million=1, output_per_million=1), "b": PriceSpec()},
    )
    problems = pricing_problems(_models("a", "b", "c"), pricing)
    assert "pricing_date não preenchido" in problems
    assert "preço zerado para: b" in problems
    assert "modelo sem preço: c" in problems
    assert not any(p.endswith(": a") for p in problems)


@pytest.mark.parametrize("field", ["temperature", "top_p", "top_k"])
def test_sampling_is_rejected_on_models_that_do_not_accept_it(field):
    with pytest.raises(ValidationError, match="effort"):
        ModelSpec(model="claude-opus-5-5", **{field: 0})
    # Haiku 4.5 ainda aceita amostragem.
    assert ModelSpec(model="claude-haiku-4-5", **{field: 0})


def test_spec_for_routes_m1_to_single_agent():
    models = _models("opus", "haiku", "tel")
    assert models.spec_for("m1", "implementer").model == "opus"
    assert models.spec_for("m2", "implementer").model == "haiku"


def test_example_configs_are_valid():
    models = load_models(ROOT / "config/models.example.yaml")
    assert {j.name for j in models.judges} == {"claude", "externo"}
    for checks in (ROOT / "config").glob("*checks*.yaml"):
        load_checks(checks)


@pytest.mark.parametrize("path", sorted((ROOT / "spec").rglob("experiment-*.yaml")))
def test_experiments_reference_existing_files(path: Path):
    experiment = load_experiment(path)
    files = [
        experiment.requirements_file,
        experiment.base_tecnica_file,
        experiment.checks_file,
        experiment.hidden_checks_file,
        *experiment.task_files,
        *experiment.context_files.values(),
        *experiment.m2_governance_files,
    ]
    for value in files:
        if value:
            assert (ROOT / value).is_file(), f"{path.name}: {value}"
    assert experiment.legacy.ref == "ac48dc552b817233547104a5d0acba932d41ab91"
