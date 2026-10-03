from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from .config import ModelsConfig, ModelSpec, Strategy
from .routing import tier_for_role


class ModelRegistry:
    def __init__(self, config: ModelsConfig, provider: str, strategy: Strategy):
        provider = {"claude": "anthropic"}.get(provider.lower(), provider.lower())
        if provider not in config.providers:
            raise ValueError(f"Provider não configurado: {provider}")
        self.provider = provider
        self.strategy = strategy
        self.provider_models = config.providers[provider]
        self._cache: dict[str, BaseChatModel] = {}

    def tier_for_role(self, role: str) -> str:
        return tier_for_role(self.strategy, role)

    def spec_for_role(self, role: str) -> tuple[str, ModelSpec]:
        tier = self.tier_for_role(role)
        return tier, getattr(self.provider_models, tier)

    def for_role(self, role: str) -> tuple[str, ModelSpec, BaseChatModel]:
        tier, spec = self.spec_for_role(role)
        cache_key = f"{self.provider}:{tier}:{spec.model}"
        if cache_key not in self._cache:
            kwargs = {
                "timeout": spec.timeout,
                "max_retries": spec.max_retries,
                **spec.extra,
            }
            if spec.reasoning_effort is not None:
                kwargs["reasoning_effort"] = spec.reasoning_effort
            if spec.temperature is not None:
                kwargs["temperature"] = spec.temperature
            if spec.max_tokens is not None:
                kwargs["max_tokens"] = spec.max_tokens

            self._cache[cache_key] = init_chat_model(
                model=spec.model,
                model_provider=self.provider,
                **kwargs,
            )
        return tier, spec, self._cache[cache_key]
