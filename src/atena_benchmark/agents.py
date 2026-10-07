from __future__ import annotations

import json
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import AIMessage

from .checks import CheckRunner
from .git_stats import diff_since, snapshot_tree
from .metrics import MetricsRecorder
from .models import ModelRegistry
from .prompts import PromptStore
from .repo_tools import build_legacy_tools, build_read_tools, build_write_tools
from .schemas import (
    ArchitecturePlan,
    PlanningOutput,
    ReviewResult,
    StepReport,
    TaskSpec,
    TelemetryRecord,
    TelemetryReport,
)

MAX_TELEMETRY_DIFF_CHARS = 60_000
MAX_TOOL_CALLS_LISTED = 300


def summarize_messages(messages: list) -> StepReport:
    """Reduz o transcript do agente ao que a telemetria precisa: mensagem final e ferramentas."""
    calls: list[str] = []
    final = ""
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            args = call.get("args") or {}
            target = args.get("path") or args.get("name") or args.get("pattern") or ""
            calls.append(f"{call.get('name')}({target})" if target else str(call.get("name")))
        if message.text:
            final = message.text
    return StepReport(
        status="completed", final_message=final, tool_calls=calls[:MAX_TOOL_CALLS_LISTED]
    )


class AgentSuite:
    """Papéis do experimento. A metodologia decide quais são usados; as ferramentas são as mesmas."""

    def __init__(
        self,
        *,
        repo_dir: Path,
        legacy_dir: Path | None,
        prompts: PromptStore,
        models: ModelRegistry,
        metrics: MetricsRecorder,
        checks: CheckRunner,
        experiment_name: str,
        tech: str,
        run_id: str,
        max_agent_steps: int = 80,
        m1_max_agent_steps: int = 400,
    ):
        self.repo_dir = repo_dir
        self.prompts = prompts
        self.models = models
        self.methodology = models.methodology
        self.metrics = metrics
        self.checks = checks
        self.experiment_name = experiment_name
        self.tech = tech
        self.run_id = run_id
        self.max_agent_steps = max_agent_steps
        self.m1_max_agent_steps = m1_max_agent_steps
        legacy_tools = build_legacy_tools(legacy_dir) if legacy_dir else []
        self.read_tools = [*build_read_tools(repo_dir, checks), *legacy_tools]
        self.write_tools = [*build_write_tools(repo_dir, checks), *legacy_tools]
        self._agents: dict[str, object] = {}

    # ---------------------------------------------------------------- infraestrutura comum

    def _build_agent(self, role: str, response_format=None, writable: bool = False):
        key = f"{role}:{getattr(response_format, '__name__', None)}:{writable}"
        if key not in self._agents:
            _, model = self.models.for_role(role)
            self._agents[key] = create_agent(
                model=model,
                tools=self.write_tools if writable else self.read_tools,
                system_prompt=self.prompts.system_prompt(self.methodology, role),
                # Saída estruturada nativa: os modelos 5.x recusam tool_choice forçado.
                response_format=ProviderStrategy(response_format) if response_format else None,
                name=f"puck_{self.methodology}_{role}",
            )
        return self._agents[key]

    def _invoke(self, role: str, agent, user_content: str, task_id: str = "", steps: int = 0):
        spec = self.models.spec_for_role(role)
        return self.metrics.measured_invoke(
            role=role,
            run_name=f"{self.experiment_name}:{self.methodology}:{role}",
            tags=["puck", self.tech, self.methodology, role],
            metadata={
                "run_id": self.run_id,
                "experiment": self.experiment_name,
                "tech": self.tech,
                "methodology": self.methodology,
                "role": role,
                "configured_model": spec.model,
                "task_id": task_id,
            },
            invoke=agent.invoke,
            payload={"messages": [{"role": "user", "content": user_content}]},
            configured_model=spec.model,
            task_id=task_id,
            # Cada passo do agente consome ~2 supersteps do grafo interno (modelo + ferramentas).
            recursion_limit=(steps or self.max_agent_steps) * 2 + 1,
        )

    def _execute(self, role: str, content: str, task_id: str, steps: int = 0) -> StepReport:
        agent = self._build_agent(role, writable=True)
        result = self._invoke(role, agent, content, task_id, steps)
        return summarize_messages(result.get("messages", []))

    def checkpoint(self) -> str:
        return snapshot_tree(self.repo_dir)

    # ---------------------------------------------------------------- M1: agente único

    def agent(self, brief: str) -> StepReport:
        content = f"""{brief}

CHECKS DISPONÍVEIS (ferramenta run_check): {json.dumps(self.checks.names(), ensure_ascii=False)}
"""
        return self._execute("agent", content, "M1", self.m1_max_agent_steps)

    # ---------------------------------------------------------------- M2: papéis

    def architect(self, brief: str, documents: list[str]) -> ArchitecturePlan:
        agent = self._build_agent("architect", ArchitecturePlan, writable=True)
        content = f"""{brief}

DOCUMENTOS A PRODUZIR EM docs/ ANTES DA IMPLEMENTAÇÃO: {", ".join(documents)}
"""
        return self._invoke("architect", agent, content)["structured_response"]

    def planner(self, brief: str, plan: ArchitecturePlan) -> PlanningOutput:
        agent = self._build_agent("planner", PlanningOutput)
        content = f"""{brief}

PLANO DO ARQUITETO:
{plan.model_dump_json(indent=2)}
"""
        return self._invoke("planner", agent, content)["structured_response"]

    def implement(self, task: TaskSpec, brief: str, plan: ArchitecturePlan) -> StepReport:
        content = f"""TAREFA:
{task.model_dump_json(indent=2)}

PLANO DO ARQUITETO:
{plan.model_dump_json(indent=2)}

CONTEXTO DO PROJETO:
{brief}

CHECKS DISPONÍVEIS (ferramenta run_check): {json.dumps(self.checks.names(), ensure_ascii=False)}
"""
        return self._execute("implementer", content, task.id)

    def repair(self, task: TaskSpec, review: ReviewResult, brief: str) -> StepReport:
        content = f"""TAREFA ORIGINAL:
{task.model_dump_json(indent=2)}

PARECER DE REPROVAÇÃO:
{review.model_dump_json(indent=2)}

CONTEXTO DO PROJETO:
{brief}
"""
        return self._execute("repair", content, task.id)

    def review(
        self,
        *,
        task: TaskSpec | None,
        brief: str,
        check_results: list[dict],
        baseline_check_results: list[dict] | None,
        final: bool = False,
    ) -> ReviewResult:
        agent = self._build_agent("reviewer", ReviewResult)
        scope = "REVISÃO FINAL DO PROJETO" if final else f"REVISÃO DA TAREFA {task.id if task else ''}"
        content = f"""{scope}

TAREFA:
{task.model_dump_json(indent=2) if task else "Revisão final de todas as alterações."}

CONTEXTO DO PROJETO:
{brief}

CHECKS NO ESQUELETO INICIAL:
{json.dumps(baseline_check_results or [], ensure_ascii=False, indent=2)}

CHECKS ATUAIS:
{json.dumps(check_results, ensure_ascii=False, indent=2)}
"""
        result = self._invoke("reviewer", agent, content, task.id if task else "FINAL")
        return result["structured_response"]

    # ---------------------------------------------------------------- telemetria (instrumento)

    def telemetry(
        self,
        *,
        stage: str,
        task_id: str,
        attempt: int,
        needs_rework: bool | None,
        since_tree: str,
        step: StepReport,
        requirements: str,
    ) -> TelemetryRecord:
        """Chamada separada, modelo fixo: extrai a telemetria do diff da etapa e do transcript.

        Falha de parse/validação não derruba a execução: vira métrica (`parse_ok = False`).
        """
        diff = diff_since(self.repo_dir, since_tree)
        truncated = len(diff) > MAX_TELEMETRY_DIFF_CHARS
        content = f"""REQUISITOS:
{requirements}

DIFF DA ETAPA ({len(diff):,} caracteres{", truncado" if truncated else ""}):
```diff
{diff[:MAX_TELEMETRY_DIFF_CHARS]}
```

FERRAMENTAS CHAMADAS PELO EXECUTOR:
{json.dumps(step.tool_calls, ensure_ascii=False)}

MENSAGEM FINAL DO EXECUTOR:
{step.final_message or "(vazia)"}
"""
        spec, model = self.models.telemetry()
        structured = model.with_structured_output(TelemetryReport, method="json_schema")
        record = {"stage": stage, "task_id": task_id, "attempt": attempt,
                  "needs_rework": needs_rework}
        try:
            report = self.metrics.measured_invoke(
                role="telemetry",
                kind="telemetry",
                run_name=f"{self.experiment_name}:telemetry",
                tags=["puck", "telemetry"],
                # Sem metodologia nem tech nos metadados enviados junto do prompt de telemetria.
                metadata={"run_id": self.run_id, "stage": stage, "task_id": task_id},
                invoke=structured.invoke,
                payload=[
                    {"role": "system", "content": self.prompts.load("telemetria")},
                    {"role": "user", "content": content},
                ],
                configured_model=spec.model,
                task_id=task_id,
            )
            if not isinstance(report, TelemetryReport):
                report = TelemetryReport.model_validate(report)
        except Exception as exc:  # parse, validação ou API: registrado como falha de telemetria
            return TelemetryRecord(**record, parse_ok=False, error=f"{type(exc).__name__}: {exc}"[:2000])
        return TelemetryRecord(**record, parse_ok=True, report=report)
