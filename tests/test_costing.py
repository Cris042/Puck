from atena_benchmark.config import PriceSpec, PricingConfig
from atena_benchmark.costing import calculate_usage_cost
from atena_benchmark.schemas import TokenUsage


def test_cost_calculation_with_cache():
    pricing = PricingConfig(
        pricing_date="2026-01-01",
        models={
            "model-x": PriceSpec(
                input_per_million=10,
                output_per_million=20,
                cache_read_per_million=1,
                cache_write_per_million=5,
            )
        },
    )
    usage = TokenUsage(
        model="model-x",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        total_tokens=2_000_000,
        cache_read_tokens=100_000,
        cache_write_tokens=100_000,
    )
    # 800k regular input = 8; output = 20; cache read = .1; cache write = .5
    assert calculate_usage_cost(usage, pricing) == 28.6


def test_unknown_model_has_zero_cost_not_guessed():
    pricing = PricingConfig(pricing_date="2026-01-01", models={})
    usage = TokenUsage(model="unknown", input_tokens=100, output_tokens=50, total_tokens=150)
    assert calculate_usage_cost(usage, pricing) == 0


def test_dated_snapshot_uses_longest_configured_prefix():
    pricing = PricingConfig(
        models={
            "gpt-x": PriceSpec(input_per_million=1, output_per_million=1),
            "gpt-x-mini": PriceSpec(input_per_million=2, output_per_million=2),
        }
    )
    usage = TokenUsage(model="gpt-x-mini-2026-05-01", input_tokens=1_000_000, total_tokens=1_000_000)
    assert calculate_usage_cost(usage, pricing) == 2


def test_falls_back_to_configured_model_when_api_name_differs():
    pricing = PricingConfig(models={"alias": PriceSpec(input_per_million=3, output_per_million=3)})
    usage = TokenUsage(model="provider/other-name", output_tokens=1_000_000, total_tokens=1_000_000)
    assert calculate_usage_cost(usage, pricing, fallback_model="alias") == 3
