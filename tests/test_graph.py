from pathlib import Path

from langgraph.errors import GraphRecursionError

from atena_benchmark.checks import CheckRunner
from atena_benchmark.config import ChecksConfig
from atena_benchmark.graph import build_graph
from atena_benchmark.schemas import (
    ArchitecturePlan,
    PlanningOutput,
    ReviewResult,
    StepReport,
    TaskSpec,
    TelemetryRecord,
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
    """Substitui as LLMs. M2: T-1 aprova de primeira, T-2 estoura o limite, T-3 nunca aprova."""

    def __init__(self, tasks: list[TaskSpec] | None = None):
        self.calls: list[str] = []
        self.tasks = tasks or []

    def checkpoint(self) -> str:
        return "tree"

    def telemetry(self, *, stage, task_id, attempt, needs_rework, since_tree, step, requirements):
        self.calls.append(f"telemetry:{stage}:{task_id}:{attempt}")
        return TelemetryRecord(
            stage=stage, task_id=task_id, attempt=attempt, needs_rework=needs_rework,
            parse_ok=task_id != "T-3",
        )

    def agent(self, brief):
        self.calls.append("agent")
        return StepReport(status="completed", final_message="STATUS: success")

    def architect(self, brief, documents):
        self.calls.append(f"architect:{','.join(documents)}")
        return ArchitecturePlan(summary="plano")

    def planner(self, brief, plan):
        self.calls.append("planner")
        return PlanningOutput(summary="x", tasks=self.tasks)

    def implement(self, task, brief, plan):
        self.calls.append(f"implement:{task.id}")
        if task.id == "T-2":
            raise GraphRecursionError("limite")
        return StepReport(status="completed", final_message="STATUS: success")

    def repair(self, task, review, brief):
        self.calls.append(f"repair:{task.id}")
        return StepReport(status="completed", final_message="STATUS: partial")

    def review(self, *, task, final=False, **kwargs):
        self.calls.append(f"review:{task.id if task else 'FINAL'}")
        return _review(final or (task is not None and task.id == "T-1"))


def _run(tmp_path: Path, methodology: str, tasks=None):
    agents = FakeAgents(tasks)
    graph = build_graph(methodology, agents, CheckRunner(tmp_path, ChecksConfig()))
    state = graph.invoke(
        {
            "brief": "b",
            "requirements": "r",
            "documents": ["ADR", "PRD"],
            "baseline_check_results": [],
            "max_repair_cycles": 2,
            "telemetry": [],
            "errors": [],
        }
    )
    return agents, state


def test_m1_is_a_single_agent_without_gates(tmp_path: Path):
    agents, state = _run(tmp_path, "m1")
    assert agents.calls == ["agent", "telemetry:agent:M1:1"]
    assert "final_review" not in state
    assert state["telemetry"][0].needs_rework is None


def test_m2_runs_roles_with_bounded_repair_and_harness_telemetry(tmp_path: Path):
    tasks = [TaskSpec(id=f"T-{i}", title=f"t{i}", description="d") for i in (1, 2, 3)]
    agents, state = _run(tmp_path, "m2", tasks)

    assert agents.calls[0] == "architect:ADR,PRD"
    assert "planner" in agents.calls
    assert state["final_review"].approved
    assert state["tasks_completed"] == 1

    outcomes = {o.task_id: o for o in state["task_outcomes"]}
    assert outcomes["T-1"].approved and outcomes["T-1"].repair_cycles == 0
    assert not outcomes["T-2"].approved and "limite" in outcomes["T-2"].error
    assert outcomes["T-3"].repair_cycles == 2  # teto respeitado
    assert agents.calls.count("repair:T-3") == 2

    kinds = {(e.stage, e.task_id): e.kind for e in state["errors"]}
    assert kinds[("implement", "T-2")] == "agent_step_limit"

    # Telemetria: uma por etapa de escrita; attempt e needs_rework vêm do harness.
    records = {(r.task_id, r.attempt): r for r in state["telemetry"]}
    assert records[("T-1", 1)].needs_rework is False
    assert records[("T-3", 1)].needs_rework is True
    assert records[("T-3", 3)].stage == "repair"
    # T-1: 1 implementação; T-2 e T-3: implementação + 2 reparos cada (estouro de passos conta
    # contra o modelo, então T-2 também entra no ciclo de reparo).
    assert len(state["telemetry"]) == 7


def test_m2_without_tasks_goes_to_final_review(tmp_path: Path):
    agents, state = _run(tmp_path, "m2", [])
    assert "planner" in agents.calls
    assert state["tasks"] == []
    assert state["final_review"].approved
