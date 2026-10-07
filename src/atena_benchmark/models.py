from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from .config import Methodology, ModelsConfig, ModelSpec


def build_chat_model(spec: ModelSpec, provider: str) -> BaseChatModel:
    kwargs = {"timeout": spec.timeout, "max_retries": spec.max_retries, **spec.extra}
    if spec.effort is not None:
        # langchain-anthropic traduz para `output_config.effort`.
        kwargs["reasoning_effort"] = spec.effort
    for key in ("max_tokens", "temperature", "top_p", "top_k"):
        value = getattr(spec, key)
        if value is not None:
            kwargs[key] = value
    return init_chat_model(model=spec.model, model_provider=provider, **kwargs)


class ModelRegistry:
    """Modelo de cada papel para uma metodologia. Na M1, todo papel é o agente único."""

    def __init__(self, config: ModelsConfig, methodology: Methodology):
        self.config = config
        self.methodology = methodology
        self._cache: dict[str, BaseChatModel] = {}

    def spec_for_role(self, role: str) -> ModelSpec:
        return self.config.spec_for(self.methodology, role)

    def for_role(self, role: str) -> tuple[ModelSpec, BaseChatModel]:
        spec = self.spec_for_role(role)
        key = spec.model_dump_json()
        if key not in self._cache:
            self._cache[key] = build_chat_model(spec, self.config.provider)
        return spec, self._cache[key]

    def telemetry(self) -> tuple[ModelSpec, BaseChatModel]:
        spec = self.config.telemetry
        key = "telemetry:" + spec.model_dump_json()
        if key not in self._cache:
            self._cache[key] = build_chat_model(spec, self.config.provider)
        return spec, self._cache[key]
