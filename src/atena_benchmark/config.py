from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class ModelSpec(BaseModel):
    model: str
    reasoning_effort: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float | None = 180
    max_retries: int = 6
    extra: dict[str, Any] = Field(default_factory=dict)


class JudgeSpec(ModelSpec):
    """Modelo avaliador fixo, igual para todas as execuções comparadas."""

    provider: str


class ProviderModels(BaseModel):
    strong: ModelSpec
    medium: ModelSpec
    weak: ModelSpec


class ModelsConfig(BaseModel):
    providers: dict[str, ProviderModels]
    judge: JudgeSpec | None = None


class PriceSpec(BaseModel):
    input_per_million: float = 0
    output_per_million: float = 0
    cache_read_per_million: float = 0
    cache_write_per_million: float = 0


class PricingConfig(BaseModel):
    pricing_date: str = "unknown"
    models: dict[str, PriceSpec] = Field(default_factory=dict)


class CheckSpec(BaseModel):
    command: list[str]
    timeout_seconds: int = 300
    required: bool = False
    # Exit codes que significam "ferramenta/suíte ausente" e não falha do código avaliado.
    # 127 é o código do shell para "command not found".
    unavailable_exit_codes: list[int] = Field(default_factory=lambda: [127])
    # Extrai contagens da saída para comparar baseline × final: "semgrep_json", "phpunit"
    # ou "line_count" (uma ocorrência por linha que começa com `line_prefix`).
    parser: Literal["semgrep_json", "phpunit", "line_count"] | None = None
    line_prefix: str = ""


class ChecksConfig(BaseModel):
    checks: dict[str, CheckSpec] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    name: str
    repository: str
    # Branch, tag ou SHA. Para benchmark, prefira SHA: branch muda entre execuções.
    base_ref: str = "main"
    requirements_file: str
    architecture_file: str
    security_file: str
    checks_file: str
    # Checks executados apenas pelo harness (baseline e final). Nunca expostos às LLMs.
    hidden_checks_file: str | None = None
    # Lista fixa de tarefas. Quando presente, o planner não é chamado e todas as execuções
    # implementam o mesmo conjunto de tarefas, o que torna os resultados comparáveis.
    tasks_file: str | None = None
    # Governança anexada ao system prompt de todos os papéis (ex.: perfil Minerva).
    governance_file: str | None = None
    max_repair_cycles: int = 2
    # Limite de passos (modelo + ferramentas) por chamada de agente. Evita loop sem fim e custo
    # descontrolado; estourar o limite conta contra o modelo, não contra o harness.
    max_agent_steps: int = 80


Strategy = Literal["single", "hierarchical"]


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_models(path: str | Path) -> ModelsConfig:
    return ModelsConfig.model_validate(load_yaml(path))


def load_pricing(path: str | Path) -> PricingConfig:
    return PricingConfig.model_validate(load_yaml(path))


def load_checks(path: str | Path) -> ChecksConfig:
    return ChecksConfig.model_validate(load_yaml(path))


def load_experiment(path: str | Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate(load_yaml(path))


def pricing_problems(models: ModelsConfig, pricing: PricingConfig) -> list[str]:
    """Lista problemas que fariam o custo ser reportado errado (silenciosamente zero)."""
    problems: list[str] = []
    if pricing.pricing_date in {"", "unknown", "YYYY-MM-DD"}:
        problems.append("pricing_date não preenchido")
    configured = {
        spec.model
        for provider in models.providers.values()
        for spec in (provider.strong, provider.medium, provider.weak)
    }
    if models.judge:
        configured.add(models.judge.model)
    for model in sorted(configured):
        price = pricing.models.get(model)
        if price is None:
            problems.append(f"modelo sem preço: {model}")
        elif price.input_per_million <= 0 or price.output_per_million <= 0:
            problems.append(f"preço zerado para: {model}")
    return problems
