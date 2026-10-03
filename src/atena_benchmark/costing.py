from __future__ import annotations

from .config import PriceSpec, PricingConfig
from .schemas import TokenUsage


def resolve_price(
    model: str, pricing: PricingConfig, fallback_model: str | None = None
) -> tuple[str, PriceSpec] | None:
    """Encontra o preço do modelo reportado pela API.

    APIs costumam devolver o snapshot datado (ex.: `gpt-x-2026-01-01`) em vez do alias
    configurado. Ordem: nome exato, maior prefixo configurado, modelo configurado no YAML.
    """
    if model in pricing.models:
        return model, pricing.models[model]
    prefixes = [name for name in pricing.models if model.startswith(name)]
    if prefixes:
        best = max(prefixes, key=len)
        return best, pricing.models[best]
    if fallback_model and fallback_model in pricing.models:
        return fallback_model, pricing.models[fallback_model]
    return None


def calculate_usage_cost(
    usage: TokenUsage, pricing: PricingConfig, fallback_model: str | None = None
) -> float:
    resolved = resolve_price(usage.model, pricing, fallback_model)
    if resolved is None:
        return 0.0
    _, price = resolved

    million = 1_000_000
    # input_tokens normally includes cache tokens in provider usage. To avoid double charging,
    # subtract known cache-read/write tokens before applying the regular input rate.
    regular_input = max(
        0,
        usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens,
    )
    return (
        regular_input / million * price.input_per_million
        + usage.output_tokens / million * price.output_per_million
        + usage.cache_read_tokens / million * price.cache_read_per_million
        + usage.cache_write_tokens / million * price.cache_write_per_million
    )
