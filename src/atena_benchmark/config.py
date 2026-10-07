from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

Effort = Literal["low", "medium", "high", "xhigh", "max"]
Methodology = Literal["m1", "m2"]

M2_ROLES = ("architect", "planner", "implementer", "reviewer", "repair")

# Modelos que rejeitam temperature/top_p/top_k com HTTP 400 e não permitem desligar o raciocínio:
# neles o único controle de geração é `effort` (+ max_tokens). Protocolo, seção 3.
NO_SAMPLING_PREFIXES = ("claude-opus-5", "claude-sonnet-5", "claude-fable-5", "claude-opus-4-7",
                        "claude-opus-4-8")


class ModelSpec(BaseModel):
    model: str
    effort: Effort | None = None
    max_tokens: int | None = None
    # Só para modelos que ainda aceitam amostragem (ex.: Haiku 4.5).
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    timeout: float | None = 600
    max_retries: int = 6
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sampling_supported(self) -> ModelSpec:
        sampling = [k for k in ("temperature", "top_p", "top_k") if getattr(self, k) is not None]
        if sampling and self.model.startswith(NO_SAMPLING_PREFIXES):
            raise ValueError(
                f"{self.model} não aceita {', '.join(sampling)}: use `effort` e `max_tokens`"
            )
        return self

    def generation_params(self) -> dict[str, Any]:
        """Parâmetros de geração declarados, como entram no snapshot e no summary."""
        keys = ("model", "effort", "max_tokens", "temperature", "top_p", "top_k")
        return {k: getattr(self, k) for k in keys if getattr(self, k) is not None}


class JudgeSpec(ModelSpec):
    """Juiz fixo da campanha. Instrumento, não sujeito: pode ser de outro provider."""

    name: str
    provider: str = "anthropic"


class M1Models(BaseModel):
    agent: ModelSpec


class M2Models(BaseModel):
    architect: ModelSpec
    planner: ModelSpec
    implementer: ModelSpec
    reviewer: ModelSpec
    repair: ModelSpec


class ModelsConfig(BaseModel):
    # Provider único dos sujeitos (protocolo, seção 1). Juízes declaram o próprio provider.
    provider: Literal["anthropic"] = "anthropic"
    m1: M1Models
    m2: M2Models
    # Chamada separada que extrai a telemetria do diff + transcript. Fixa e barata.
    telemetry: ModelSpec
    judges: list[JudgeSpec] = Field(default_factory=list)

    def spec_for(self, methodology: Methodology, role: str) -> ModelSpec:
        if methodology == "m1":
            return self.m1.agent
        return getattr(self.m2, role)

    def all_specs(self) -> list[ModelSpec]:
        return [
            self.m1.agent,
            *(getattr(self.m2, role) for role in M2_ROLES),
            self.telemetry,
            *self.judges,
        ]


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
    # Extrai contagens da saída para comparar baseline × final: "semgrep_json", "phpunit",
    # "line_count" (uma ocorrência por linha que começa com `line_prefix`) ou "puck_metrics"
    # (linhas `PUCK_METRIC <nome> <inteiro>`).
    parser: Literal["semgrep_json", "phpunit", "line_count", "puck_metrics"] | None = None
    line_prefix: str = ""


class ChecksConfig(BaseModel):
    checks: dict[str, CheckSpec] = Field(default_factory=dict)


class RepoRef(BaseModel):
    # URL ou caminho local. Para benchmark, `ref` deve ser SHA: branch muda entre execuções.
    repository: str
    ref: str


class ExperimentConfig(BaseModel):
    name: str
    tech: str
    # Esqueleto mínimo fixo da tech: ponto de partida do workspace, idêntico em M1 e M2.
    scaffold: RepoRef
    # Sistema legado: referência somente-leitura (fonte dos requisitos e do comportamento).
    legacy: RepoRef
    # Repositórios que só têm o SHA registrado (ex.: Minerva, MinervaFinancas).
    references: dict[str, RepoRef] = Field(default_factory=dict)
    requirements_file: str
    # Base técnica comum (constante entre células) e tarefas entregues às duas metodologias.
    base_tecnica_file: str
    # Anexos normativos entregues na íntegra (ex.: contrato HTTP em OpenAPI).
    spec_files: list[str] = Field(default_factory=list)
    task_files: list[str] = Field(default_factory=list)
    # Arquivos que preenchem placeholders `{nome}` nas tarefas (ex.: mer_der).
    context_files: dict[str, str] = Field(default_factory=dict)
    checks_file: str
    # Checks executados apenas pelo harness (baseline e final). Nunca expostos às LLMs.
    hidden_checks_file: str | None = None
    # Governança da M2 (inspirada no Minerva): anexada só aos papéis da M2.
    m2_governance_files: list[str] = Field(default_factory=list)
    # Documentos que o arquiteto da M2 produz no workspace antes de implementar.
    m2_documents: list[str] = Field(default_factory=lambda: ["ADR", "PRD", "HLD", "FDD"])
    max_repair_cycles: int = 2
    # Limite de passos (modelo + ferramentas) por chamada de agente na M2. Estourar conta contra o
    # modelo, não contra o harness.
    max_agent_steps: int = 80
    # A M1 faz tudo numa única sessão de agente, então recebe um teto proporcionalmente maior.
    m1_max_agent_steps: int = 400


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
    for model in sorted({spec.model for spec in models.all_specs()}):
        price = pricing.models.get(model)
        if price is None:
            problems.append(f"modelo sem preço: {model}")
        elif price.input_per_million <= 0 or price.output_per_million <= 0:
            problems.append(f"preço zerado para: {model}")
    return problems
