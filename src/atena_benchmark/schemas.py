from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Decision(BaseModel):
    decision: str
    reason: str
    trade_off: str = ""
    requirement: str = ""


class ArchitecturePlan(BaseModel):
    summary: str
    problems: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    constraints_for_implementation: list[str] = Field(default_factory=list)
    affected_areas: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    explicitly_not_doing: list[str] = Field(default_factory=list)
    # Caminhos dos documentos (ADR/PRD/HLD/FDD) gravados no workspace pelo arquiteto da M2.
    documents_written: list[str] = Field(default_factory=list)


class TaskSpec(BaseModel):
    id: str
    title: str
    requirements: list[str] = Field(default_factory=list)
    description: str
    expected_behavior: list[str] = Field(default_factory=list)
    likely_files: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)


class PlanningOutput(BaseModel):
    summary: str
    tasks: list[TaskSpec]


class StepReport(BaseModel):
    """Saída de uma chamada de execução (implementar, reparar, agente único).

    Texto livre do executor: a telemetria estruturada sai de uma chamada separada, para não
    ensinar o executor a se autoavaliar e para seus tokens não entrarem no custo de execução.
    """

    status: Literal["completed", "failed"]
    final_message: str = ""
    tool_calls: list[str] = Field(default_factory=list)


Confidence = Literal["high", "medium", "low"]


class RequirementTelemetry(BaseModel):
    id: str
    # IMPLEMENTADO × VALIDADO: validado só com teste/check executado que exercita o requisito.
    state: Literal["validated", "implemented", "not_implemented"]
    confidence: Confidence
    evidence: str = ""


class TelemetryReport(BaseModel):
    """Extraída do diff + transcript por um modelo fixo; validada com Pydantic."""

    declared_status: Literal["success", "partial", "failed", "unknown"] = Field(
        description="Status que o EXECUTOR declarou no transcript; unknown se não declarou."
    )
    requirements: list[RequirementTelemetry] = Field(default_factory=list)
    tests_executed: list[str] = Field(default_factory=list)
    tests_failed: list[str] = Field(default_factory=list)
    possible_regressions: list[str] = Field(default_factory=list)
    architecture_violations: list[str] = Field(default_factory=list)
    security_risks: list[str] = Field(default_factory=list)
    abstractions_created: list[str] = Field(default_factory=list)
    dependencies_added: list[str] = Field(default_factory=list)
    overengineering_signals: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    # Preenchido pela validação, não pelo modelo.
    possible_regressions_rejected: bool = False

    @model_validator(mode="after")
    def _regressions_need_tests(self) -> TelemetryReport:
        # Regressão "possível" sem nenhum teste executado é palpite: não entra na métrica.
        if self.possible_regressions and not self.tests_executed:
            self.possible_regressions = []
            self.possible_regressions_rejected = True
        return self


class TelemetryRecord(BaseModel):
    """Envelope do harness: attempt e needs_rework vêm do harness, nunca do modelo."""

    stage: str
    task_id: str = ""
    attempt: int = 1
    needs_rework: bool | None = None
    parse_ok: bool
    error: str = ""
    report: TelemetryReport | None = None


class CheckResult(BaseModel):
    name: str
    command: list[str]
    exit_code: int
    status: Literal["passed", "failed", "unavailable", "timeout", "error"]
    required: bool
    duration_ms: float
    output: str
    # Contagens extraídas pelo parser do check (ex.: achados por regra Semgrep, testes PHPUnit).
    counts: dict[str, int] = Field(default_factory=dict)


class ReviewResult(BaseModel):
    approved: bool
    summary: str
    requirements_ok: bool
    architecture_ok: bool
    security_ok: bool
    overengineering_ok: bool
    requirements_gaps: list[str] = Field(default_factory=list)
    architecture_violations: list[str] = Field(default_factory=list)
    security_findings: list[str] = Field(default_factory=list)
    overengineering_findings: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)
    possible_regressions: list[str] = Field(default_factory=list)


class TokenUsage(BaseModel):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    # Nome da tabela de preços usado no cálculo; vazio quando o modelo não tem preço.
    priced_as: str = ""


class InvocationMetric(BaseModel):
    role: str
    # execution entra no custo da metodologia; telemetry, judge e instrument (ex.: contaminação)
    # são instrumento, medidos à parte.
    kind: Literal["execution", "telemetry", "judge", "instrument"] = "execution"
    model: str = ""
    started_at: str = ""
    duration_ms: float
    task_id: str = ""
    usages: list[TokenUsage] = Field(default_factory=list)
    estimated_cost_usd: float = 0
    error: str = ""


ErrorKind = Literal["agent_step_limit", "invalid_output", "infra"]


class RunError(BaseModel):
    """Falha durante a execução.

    `agent_step_limit` e `invalid_output` contam contra o modelo. `infra` (rede, rate limit,
    autenticação, bug do harness) invalida a execução: ela deve ser repetida, não pontuada.
    """

    stage: str
    task_id: str = ""
    kind: ErrorKind
    message: str


class TaskOutcome(BaseModel):
    task_id: str
    title: str = ""
    approved: bool = False
    repair_cycles: int = 0
    implementation_status: str = ""
    error: str = ""


class ExperimentSummary(BaseModel):
    run_id: str
    experiment: str
    tech: str
    methodology: str
    # SHA efetivo de cada repositório envolvido (workspace, legado, referências).
    source_shas: dict[str, str] = Field(default_factory=dict)
    # Parâmetros de geração por papel, como declarados no models.yaml.
    generation_params: dict[str, dict] = Field(default_factory=dict)
    valid: bool = True
    started_at: str
    finished_at: str
    pricing_date: str
    total_duration_ms: float
    # Custo e tokens de EXECUÇÃO (o que a metodologia consumiu).
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int = 0
    total_tokens: int
    # Telemetria: instrumento, nunca somada ao custo da metodologia.
    telemetry_cost_usd: float = 0
    telemetry_tokens: int = 0
    telemetry_records: int = 0
    telemetry_parse_failures: int = 0
    repair_cycles: int = 0
    tasks_total: int = 0
    tasks_completed: int = 0
    final_review: ReviewResult | None = None
    task_outcomes: list[TaskOutcome] = Field(default_factory=list)
    errors: list[RunError] = Field(default_factory=list)
    unpriced_models: list[str] = Field(default_factory=list)
    baseline_checks: list[CheckResult] = Field(default_factory=list)
    deterministic_checks: list[CheckResult] = Field(default_factory=list)
    hidden_baseline_checks: list[CheckResult] = Field(default_factory=list)
    hidden_final_checks: list[CheckResult] = Field(default_factory=list)
    invocations: list[InvocationMetric] = Field(default_factory=list)


class DimensionScore(BaseModel):
    score: int = Field(ge=1, le=5, description="1 = muito ruim, 3 = aceitável, 5 = excelente")
    justification: str


class JudgeFinding(BaseModel):
    severity: Literal["blocking", "non_blocking"]
    dimension: Literal[
        "requirements", "regressions", "architecture", "security", "simplicity", "tests"
    ]
    description: str
    evidence: str = ""


class EvaluationResult(BaseModel):
    """Avaliação cega e independente produzida por um juiz fixo após a execução."""

    requirements: DimensionScore
    regressions: DimensionScore
    architecture: DimensionScore
    security: DimensionScore
    simplicity: DimensionScore
    tests: DimensionScore
    findings: list[JudgeFinding] = Field(default_factory=list)
    summary: str
