from atena_benchmark.config import (
    ModelsConfig,
    ModelSpec,
    PriceSpec,
    PricingConfig,
    ProviderModels,
    pricing_problems,
)


def _models(*names: str) -> ModelsConfig:
    strong, medium, weak = names
    return ModelsConfig(
        providers={
            "p": ProviderModels(
                strong=ModelSpec(model=strong), medium=ModelSpec(model=medium), weak=ModelSpec(model=weak)
            )
        }
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
