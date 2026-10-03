from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain.agents.structured_output import StructuredOutputError
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .agents import AgentSuite
from .checks import CheckRunner
from .schemas import (
    ArchitecturePlan,
    CheckResult,
    ExecutionReport,
    ReviewResult,
    RunError,
    TaskOutcome,
    TaskSpec,
)


class ExperimentState(TypedDict, total=False):
    requirements: str
    architecture: str
    security: str
    fixed_tasks: list[TaskSpec]
    architecture_plan: ArchitecturePlan
    tasks: list[TaskSpec]
    task_index: int
    current_report: ExecutionReport
    execution_reports: list[ExecutionReport]
    baseline_check_results: list[CheckResult]
    check_results: list[CheckResult]
    last_review: ReviewResult
    final_review: ReviewResult
    task_repair_cycle: int
    total_repair_cycles: int
    tasks_completed: int
    task_outcomes: list[TaskOutcome]
    max_repair_cycles: int
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


def _failed_report(error: RunError) -> ExecutionReport:
    return ExecutionReport(status="failed", summary=f"Agente não concluiu: {error.message}")


def _failed_review(error: RunError) -> ReviewResult:
    return ReviewResult(
        approved=False,
        summary=f"Revisão não concluída: {error.message}",
        requirements_ok=False,
        architecture_ok=False,
        security_ok=False,
        overengineering_ok=False,
    )


def build_graph(agents: AgentSuite, checks: CheckRunner):
    graph = StateGraph(ExperimentState)

    def architect_node(state: ExperimentState):
        try:
            plan = agents.architect(
                state["requirements"], state["architecture"], state["security"]
            )
        except Exception as exc:
            error = classify_error("architect", exc)
            # Sem plano não há o que implementar de forma comparável: encerra com revisão final.
            return {
                "architecture_plan": ArchitecturePlan(summary=f"Falha: {error.message}"),
                "errors": [error],
                "aborted": True,
            }
        return {"architecture_plan": plan}

    def planner_node(state: ExperimentState):
        base = {
            "task_index": 0,
            "execution_reports": [],
            "task_repair_cycle": 0,
            "total_repair_cycles": 0,
            "tasks_completed": 0,
            "task_outcomes": [],
        }
        if state.get("aborted"):
            return {**base, "tasks": []}
        if state.get("fixed_tasks"):
            return {**base, "tasks": list(state["fixed_tasks"])}
        try:
            planning = agents.planner(
                state["requirements"], state["architecture"], state["architecture_plan"]
            )
        except Exception as exc:
            return {**base, "tasks": [], "errors": [classify_error("planner", exc)]}
        return {**base, "tasks": planning.tasks}

    def implement_node(state: ExperimentState):
        task = state["tasks"][state["task_index"]]
        errors = []
        try:
            report = agents.implement(
                task,
                state["architecture"],
                state["security"],
                state["architecture_plan"],
            )
        except Exception as exc:
            error = classify_error("implement", exc, task.id)
            errors.append(error)
            report = _failed_report(error)
        reports = list(state.get("execution_reports", []))
        reports.append(report)
        return {"current_report": report, "execution_reports": reports, "errors": errors}

    def validate_node(state: ExperimentState):
        return {"check_results": checks.run_all()}

    def review_node(state: ExperimentState):
        task = state["tasks"][state["task_index"]]
        errors = []
        try:
            review = agents.review(
                task=task,
                requirements=state["requirements"],
                architecture=state["architecture"],
                security=state["security"],
                check_results=[x.model_dump() for x in state.get("check_results", [])],
                baseline_check_results=[
                    x.model_dump() for x in state.get("baseline_check_results", [])
                ],
                implementation_report=state.get("current_report"),
            )
        except Exception as exc:
            error = classify_error("review", exc, task.id)
            errors.append(error)
            review = _failed_review(error)
        return {"last_review": review, "errors": errors}

    def repair_node(state: ExperimentState):
        task = state["tasks"][state["task_index"]]
        errors = []
        try:
            report = agents.repair(
                task,
                state["last_review"],
                state["architecture"],
                state["security"],
            )
        except Exception as exc:
            error = classify_error("repair", exc, task.id)
            errors.append(error)
            report = _failed_report(error)
        reports = list(state.get("execution_reports", []))
        reports.append(report)
        return {
            "current_report": report,
            "execution_reports": reports,
            "task_repair_cycle": state.get("task_repair_cycle", 0) + 1,
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
                requirements=state["requirements"],
                architecture=state["architecture"],
                security=state["security"],
                check_results=[x.model_dump() for x in final_checks],
                baseline_check_results=[
                    x.model_dump() for x in state.get("baseline_check_results", [])
                ],
                implementation_report=None,
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
