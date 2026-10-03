from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


class RequirementMetrics(BaseModel):
    addressed: list[str] = Field(default_factory=list)
    not_addressed: list[str] = Field(default_factory=list)
    possible_regressions: list[str] = Field(default_factory=list)


class ArchitectureMetrics(BaseModel):
    followed: bool = True
    violations: list[str] = Field(default_factory=list)


class ImplementationMetrics(BaseModel):
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    dependencies_added: list[str] = Field(default_factory=list)
    abstractions_created: list[str] = Field(default_factory=list)


class SecurityMetrics(BaseModel):
    issues_found: list[str] = Field(default_factory=list)
    issues_fixed: list[str] = Field(default_factory=list)
    possible_new_risks: list[str] = Field(default_factory=list)


class OverengineeringMetrics(BaseModel):
    detected: bool = False
    items: list[str] = Field(default_factory=list)


class ValidationMetrics(BaseModel):
    tests_executed: list[str] = Field(default_factory=list)
    tests_failed: list[str] = Field(default_factory=list)
    not_validated: list[str] = Field(default_factory=list)


class ReworkMetrics(BaseModel):
    required: bool = False
    reason: str = ""


class ExecutionReport(BaseModel):
    status: Literal["success", "partial", "failed"]
    summary: str
    requirements: RequirementMetrics = Field(default_factory=RequirementMetrics)
    architecture: ArchitectureMetrics = Field(default_factory=ArchitectureMetrics)
    implementation: ImplementationMetrics = Field(default_factory=ImplementationMetrics)
    security: SecurityMetrics = Field(default_factory=SecurityMetrics)
    overengineering: OverengineeringMetrics = Field(default_factory=OverengineeringMetrics)
    validation: ValidationMetrics = Field(default_factory=ValidationMetrics)
    rework: ReworkMetrics = Field(default_factory=ReworkMetrics)
    decisions: list[Decision] = Field(default_factory=list)


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
    tier: str
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
    provider: str
    strategy: str
    governance: str = "none"
    base_commit: str = ""
    task_source: Literal["planner", "fixed"] = "planner"
    valid: bool = True
    started_at: str
    finished_at: str
    pricing_date: str
    total_duration_ms: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    repair_cycles: int
    tasks_total: int
    tasks_completed: int
    final_review: ReviewResult | None = None
    task_outcomes: list[TaskOutcome] = Field(default_factory=list)
    errors: list[RunError] = Field(default_factory=list)
    unpriced_models: list[str] = Field(default_factory=list)
    baseline_checks: list[CheckResult] = Field(default_factory=list)
    deterministic_checks: list[CheckResult] = Field(default_factory=list)
    hidden_baseline_checks: list[CheckResult] = Field(default_factory=list)
    hidden_final_checks: list[CheckResult] = Field(default_factory=list)
    invocations: list[InvocationMetric] = Field(default_factory=list)


class TasksFile(BaseModel):
    tasks: list[TaskSpec]


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
