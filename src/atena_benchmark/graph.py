from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain.agents.structured_output import StructuredOutputError
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .checks import CheckRunner
from .schemas import (
    ArchitecturePlan,
    CheckResult,
    ReviewResult,
    RunError,
    StepReport,
    TaskOutcome,
    TaskSpec,
    TelemetryRecord,
)


class ExperimentState(TypedDict, total=False):
    # Entrada montada pelo runner: requisitos + base técnica + tarefas (igual para M1 e M2).
    brief: str
    requirements: str
    documents: list[str]
    architecture_plan: ArchitecturePlan
    tasks: list[TaskSpec]
    task_index: int
    current_report: StepReport
    baseline_check_results: list[CheckResult]
    check_results: list[CheckResult]
    last_review: ReviewResult
    final_review: ReviewResult
    task_repair_cycle: int
    total_repair_cycles: int
    tasks_completed: int
    task_outcomes: list[TaskOutcome]
    max_repair_cycles: int
    telemetry: list[TelemetryRecord]
    errors: Annotated[list[RunError], operator.add]
    aborted: bool


def classify_error(stage: str, exc: Exception, task_id: str = "") -> RunError:
    if isinstance(exc, GraphRecursionError):
        kind = "agent_step_limit"
    elif isinstance(exc, (StructuredOutputError, ValidationError, KeyError)):
        kind = "invalid_output"
    else:
        kind = "infra"
    return RunError(
        stage=stage, task_id=task_id, kind=kind, message=f"{type(exc).__name__}: {exc}"[:2000]
    )


def _failed_step(error: RunError) -> StepReport:
    return StepReport(status="failed", final_message=f"Agente não concluiu: {error.message}")


def _failed_review(error: RunError) -> ReviewResult:
    return ReviewResult(
        approved=False,
        summary=f"Revisão não concluída: {error.message}",
        requirements_ok=False,
        architecture_ok=False,
        security_ok=False,
        overengineering_ok=False,
    )


def _run_step(agents, state: ExperimentState, *, stage: str, task_id: str, attempt: int, call):
    """Executa uma etapa de escrita e a telemetria dela (chamada separada)."""
    tree = agents.checkpoint()
    errors: list[RunError] = []
    try:
        report = call()
    except Exception as exc:
        error = classify_error(stage, exc, task_id)
        errors.append(error)
        report = _failed_step(error)
    record = agents.telemetry(
        stage=stage,
        task_id=task_id,
        attempt=attempt,
        needs_rework=None,
        since_tree=tree,
        step=report,
        requirements=state["requirements"],
    )
    return report, record, errors


def build_m1_graph(agents, checks: CheckRunner):
    """M1 — direta: um agente, uma sessão, sem documentos, gates nem reparo."""
    graph = StateGraph(ExperimentState)

    def agent_node(state: ExperimentState):
        report, record, errors = _run_step(
            agents, state, stage="agent", task_id="M1", attempt=1,
            call=lambda: agents.agent(state["brief"]),
        )
        return {"current_report": report, "telemetry": [record], "errors": errors}

    def final_checks_node(state: ExperimentState):
        # Medição do harness: o resultado não volta para o agente.
        return {"check_results": checks.run_all()}

    graph.add_node("agent", agent_node)
    graph.add_node("final_checks", final_checks_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", "final_checks")
    graph.add_edge("final_checks", END)
    return graph.compile()


def build_m2_graph(agents, checks: CheckRunner):
    """M2 — governada: Arquiteto → Planner → (Implementador → checks → Revisor → Reparo)* → final."""
    graph = StateGraph(ExperimentState)

    def architect_node(state: ExperimentState):
        try:
            plan = agents.architect(state["brief"], state.get("documents", []))
        except Exception as exc:
            error = classify_error("architect", exc)
            # Sem plano não há o que implementar: encerra com revisão final.
            return {
                "architecture_plan": ArchitecturePlan(summary=f"Falha: {error.message}"),
                "errors": [error],
                "aborted": True,
            }
        return {"architecture_plan": plan}

    def planner_node(state: ExperimentState):
        base = {
            "task_index": 0,
            "task_repair_cycle": 0,
            "total_repair_cycles": 0,
            "tasks_completed": 0,
            "task_outcomes": [],
            "telemetry": [],
        }
        if state.get("aborted"):
            return {**base, "tasks": []}
        try:
            planning = agents.planner(state["brief"], state["architecture_plan"])
        except Exception as exc:
            return {**base, "tasks": [], "errors": [classify_error("planner", exc)]}
        return {**base, "tasks": planning.tasks}

    def implement_node(state: ExperimentState):
        task = state["tasks"][state["task_index"]]
        report, record, errors = _run_step(
            agents, state, stage="implement", task_id=task.id, attempt=1,
            call=lambda: agents.implement(task, state["brief"], state["architecture_plan"]),
        )
        return {
            "current_report": report,
            "telemetry": [*state.get("telemetry", []), record],
            "errors": errors,
        }

    def validate_node(state: ExperimentState):
        return {"check_results": checks.run_all()}

    def review_node(state: ExperimentState):
        task = state["tasks"][state["task_index"]]
        errors = []
        try:
            review = agents.review(
                task=task,
                brief=state["brief"],
                check_results=[x.model_dump() for x in state.get("check_results", [])],
                baseline_check_results=[
                    x.model_dump() for x in state.get("baseline_check_results", [])
                ],
            )
        except Exception as exc:
            error = classify_error("review", exc, task.id)
            errors.append(error)
            review = _failed_review(error)
        # needs_rework vem do harness (veredito do revisor), nunca do executor.
        telemetry = list(state.get("telemetry", []))
        if telemetry and telemetry[-1].task_id == task.id:
            telemetry[-1] = telemetry[-1].model_copy(update={"needs_rework": not review.approved})
        return {"last_review": review, "telemetry": telemetry, "errors": errors}

    def repair_node(state: ExperimentState):
        task = state["tasks"][state["task_index"]]
        cycle = state.get("task_repair_cycle", 0) + 1
        report, record, errors = _run_step(
            agents, state, stage="repair", task_id=task.id, attempt=cycle + 1,
            call=lambda: agents.repair(task, state["last_review"], state["brief"]),
        )
        return {
            "current_report": report,
            "telemetry": [*state.get("telemetry", []), record],
            "task_repair_cycle": cycle,
            "total_repair_cycles": state.get("total_repair_cycles", 0) + 1,
            "errors": errors,
        }

    def advance_node(state: ExperimentState):
        task = state["tasks"][state["task_index"]]
        review = state.get("last_review")
        approved = review is not None and review.approved
        report = state.get("current_report")
        task_errors = [e.message for e in state.get("errors", []) if e.task_id == task.id]
        outcome = TaskOutcome(
            task_id=task.id,
            title=task.title,
            approved=approved,
            repair_cycles=state.get("task_repair_cycle", 0),
            implementation_status=report.status if report else "",
            error=" | ".join(task_errors)[:2000],
        )
        return {
            "task_index": state["task_index"] + 1,
            "task_repair_cycle": 0,
            "tasks_completed": state.get("tasks_completed", 0) + (1 if approved else 0),
            "task_outcomes": [*state.get("task_outcomes", []), outcome],
        }

    def final_review_node(state: ExperimentState):
        final_checks = checks.run_all()
        errors = []
        try:
            review = agents.review(
                task=None,
                brief=state["brief"],
                check_results=[x.model_dump() for x in final_checks],
                baseline_check_results=[
                    x.model_dump() for x in state.get("baseline_check_results", [])
                ],
                final=True,
            )
        except Exception as exc:
            error = classify_error("final_review", exc, "FINAL")
            errors.append(error)
            review = _failed_review(error)
        return {"check_results": final_checks, "final_review": review, "errors": errors}

    def after_planner(state: ExperimentState) -> str:
        return "implement" if state.get("tasks") else "final_review"

    def after_review(state: ExperimentState) -> str:
        if state["last_review"].approved:
            return "advance"
        # Repetir reparo após falha de infraestrutura só gasta tokens; segue para a próxima tarefa.
        task = state["tasks"][state["task_index"]]
        if any(e.kind == "infra" and e.task_id == task.id for e in state.get("errors", [])):
            return "advance"
        if state.get("task_repair_cycle", 0) < state.get("max_repair_cycles", 2):
            return "repair"
        return "advance"

    def after_advance(state: ExperimentState) -> str:
        if state["task_index"] < len(state.get("tasks", [])):
            return "implement"
        return "final_review"

    graph.add_node("architect", architect_node)
    graph.add_node("planner", planner_node)
    graph.add_node("implement", implement_node)
    graph.add_node("validate", validate_node)
    graph.add_node("review", review_node)
    graph.add_node("repair", repair_node)
    graph.add_node("advance", advance_node)
    graph.add_node("final_review", final_review_node)

    graph.add_edge(START, "architect")
    graph.add_edge("architect", "planner")
    graph.add_conditional_edges(
        "planner", after_planner, {"implement": "implement", "final_review": "final_review"}
    )
    graph.add_edge("implement", "validate")
    graph.add_edge("validate", "review")
    graph.add_conditional_edges(
        "review", after_review, {"repair": "repair", "advance": "advance"}
    )
    graph.add_edge("repair", "validate")
    graph.add_conditional_edges(
        "advance", after_advance, {"implement": "implement", "final_review": "final_review"}
    )
    graph.add_edge("final_review", END)
    return graph.compile()


def build_graph(methodology: str, agents, checks: CheckRunner):
    return build_m1_graph(agents, checks) if methodology == "m1" else build_m2_graph(agents, checks)
