from pathlib import Path

from langgraph.errors import GraphRecursionError

from atena_benchmark.checks import CheckRunner
from atena_benchmark.config import ChecksConfig
from atena_benchmark.graph import build_graph
from atena_benchmark.schemas import (
    ArchitecturePlan,
    ExecutionReport,
    PlanningOutput,
    ReviewResult,
    TaskSpec,
)


def _review(approved: bool) -> ReviewResult:
    return ReviewResult(
        approved=approved,
        summary="ok" if approved else "ajustar",
        requirements_ok=approved,
        architecture_ok=True,
        security_ok=True,
        overengineering_ok=True,
    )


class FakeAgents:
    """Substitui as LLMs: T-1 aprova de primeira, T-2 estoura o limite, T-3 nunca aprova."""

    def __init__(self):
        self.calls: list[str] = []

    def architect(self, *args):
        self.calls.append("architect")
        return ArchitecturePlan(summary="plano")

    def planner(self, *args):
        self.calls.append("planner")
        return PlanningOutput(summary="x", tasks=[])

    def implement(self, task, *args):
        self.calls.append(f"implement:{task.id}")
        if task.id == "T-2":
            raise GraphRecursionError("limite")
        return ExecutionReport(status="success", summary="feito")

    def repair(self, task, *args):
        self.calls.append(f"repair:{task.id}")
        return ExecutionReport(status="partial", summary="corrigido")

    def review(self, *, task, final=False, **kwargs):
        self.calls.append(f"review:{task.id if task else 'FINAL'}")
        return _review(final or (task is not None and task.id == "T-1"))


def _run(tmp_path: Path, fixed_tasks):
    agents = FakeAgents()
    graph = build_graph(agents, CheckRunner(tmp_path, ChecksConfig()))
    state = graph.invoke(
        {
            "requirements": "r",
            "architecture": "a",
            "security": "s",
            "fixed_tasks": fixed_tasks,
            "baseline_check_results": [],
            "max_repair_cycles": 2,
            "errors": [],
        }
    )
    return agents, state


def test_fixed_tasks_skip_planner_and_failures_do_not_abort_run(tmp_path: Path):
    tasks = [TaskSpec(id=f"T-{i}", title=f"t{i}", description="d") for i in (1, 2, 3)]
    agents, state = _run(tmp_path, tasks)

    assert "planner" not in agents.calls
    assert state["final_review"].approved
    assert state["tasks_completed"] == 1

    outcomes = {o.task_id: o for o in state["task_outcomes"]}
    assert outcomes["T-1"].approved and outcomes["T-1"].repair_cycles == 0
    assert not outcomes["T-2"].approved and "limite" in outcomes["T-2"].error
    assert outcomes["T-3"].repair_cycles == 2  # teto respeitado

    kinds = {(e.stage, e.task_id): e.kind for e in state["errors"]}
    assert kinds[("implement", "T-2")] == "agent_step_limit"
    assert agents.calls.count("repair:T-3") == 2


def test_planner_is_used_without_fixed_tasks(tmp_path: Path):
    agents, state = _run(tmp_path, [])
    assert "planner" in agents.calls
    assert state["tasks"] == []
