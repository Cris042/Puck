from __future__ import annotations

import json
from pathlib import Path

from langchain.agents import create_agent

from .checks import CheckRunner
from .metrics import MetricsRecorder
from .models import ModelRegistry
from .prompts import PromptStore
from .repo_tools import build_read_tools, build_write_tools
from .schemas import (
    ArchitecturePlan,
    ExecutionReport,
    PlanningOutput,
    ReviewResult,
    TaskSpec,
)


class AgentSuite:
    def __init__(
        self,
        *,
        repo_dir: Path,
        prompts: PromptStore,
        models: ModelRegistry,
        metrics: MetricsRecorder,
        checks: CheckRunner,
        experiment_name: str,
        provider: str,
        strategy: str,
        run_id: str,
        max_agent_steps: int = 80,
    ):
        self.repo_dir = repo_dir
        self.prompts = prompts
        self.models = models
        self.metrics = metrics
        self.checks = checks
        self.experiment_name = experiment_name
        self.provider = provider
        self.strategy = strategy
        self.run_id = run_id
        self.max_agent_steps = max_agent_steps
        self.read_tools = build_read_tools(repo_dir, checks)
        self.write_tools = build_write_tools(repo_dir, checks)
        self._agents: dict[str, object] = {}

    def _build_agent(self, role: str, response_format, writable: bool = False):
        key = f"{role}:{response_format.__name__}:{writable}"
        if key in self._agents:
            return self._agents[key]
        _, _, model = self.models.for_role(role)
        agent = create_agent(
            model=model,
            tools=self.write_tools if writable else self.read_tools,
            system_prompt=self.prompts.system_prompt(role),
            response_format=response_format,
            name=f"atena_benchmark_{role}",
        )
        self._agents[key] = agent
        return agent

    def _invoke(self, role: str, agent, user_content: str, task_id: str = ""):
        tier, spec = self.models.spec_for_role(role)
        return self.metrics.measured_invoke(
            role=role,
            tier=tier,
            run_name=f"{self.experiment_name}:{role}",
            tags=["atena-benchmark", self.provider, self.strategy, role, tier],
            metadata={
                "run_id": self.run_id,
                "experiment": self.experiment_name,
                "provider": self.provider,
                "strategy": self.strategy,
                "role": role,
                "tier": tier,
                "configured_model": spec.model,
                "task_id": task_id,
            },
            invoke=agent.invoke,
            payload={"messages": [{"role": "user", "content": user_content}]},
            configured_model=spec.model,
            task_id=task_id,
            # Cada passo do agente consome ~2 supersteps do grafo interno (modelo + ferramentas).
            recursion_limit=self.max_agent_steps * 2 + 1,
        )

    def architect(self, requirements: str, architecture: str, security: str) -> ArchitecturePlan:
        agent = self._build_agent("architect", ArchitecturePlan)
        prompt = f"""
Analise o repositório real usando as ferramentas disponíveis e produza o plano arquitetural mínimo necessário.

REQUISITOS:\n{requirements}

ARQUITETURA/RESTRIÇÕES OBRIGATÓRIAS:\n{architecture}

SEGURANÇA:\n{security}

Não implemente código. Não redesenhe o sistema por preferência pessoal. Registre explicitamente o que NÃO deve ser feito para evitar overengineering.
"""
        result = self._invoke("architect", agent, prompt)
        return result["structured_response"]

    def planner(
        self,
        requirements: str,
        architecture: str,
        plan: ArchitecturePlan,
    ) -> PlanningOutput:
        agent = self._build_agent("planner", PlanningOutput)
        prompt = f"""
Transforme o plano arquitetural em uma sequência curta de tarefas implementáveis.
Cada tarefa deve ser pequena, verificável e vinculada a requisitos concretos.
Não adicione escopo.

REQUISITOS:\n{requirements}

ARQUITETURA:\n{architecture}

PLANO DO ARQUITETO:\n{plan.model_dump_json(indent=2)}
"""
        result = self._invoke("planner", agent, prompt)
        return result["structured_response"]

    def implement(
        self,
        task: TaskSpec,
        architecture: str,
        security: str,
        architecture_plan: ArchitecturePlan,
    ) -> ExecutionReport:
        agent = self._build_agent("implementer", ExecutionReport, writable=True)
        prompt = f"""
Implemente SOMENTE a tarefa abaixo no workspace usando as ferramentas de leitura/escrita.
Antes de concluir, execute os checks relevantes disponíveis quando isso for possível.

TAREFA:\n{task.model_dump_json(indent=2)}

ARQUITETURA OBRIGATÓRIA:\n{architecture}

SEGURANÇA:\n{security}

DECISÕES DO ARQUITETO:\n{architecture_plan.model_dump_json(indent=2)}

CHECKS DISPONÍVEIS:\n{json.dumps(self.checks.names(), ensure_ascii=False)}

Não faça refatorações laterais que não sejam necessárias para a tarefa.
"""
        result = self._invoke("implementer", agent, prompt, task.id)
        return result["structured_response"]

    def repair(
        self,
        task: TaskSpec,
        review: ReviewResult,
        architecture: str,
        security: str,
    ) -> ExecutionReport:
        agent = self._build_agent("repair", ExecutionReport, writable=True)
        prompt = f"""
Corrija SOMENTE os problemas encontrados na revisão da tarefa. Não expanda o escopo.

TAREFA ORIGINAL:\n{task.model_dump_json(indent=2)}

REVISÃO:\n{review.model_dump_json(indent=2)}

ARQUITETURA:\n{architecture}

SEGURANÇA:\n{security}

Use o menor conjunto de mudanças necessário e execute os checks relevantes.
"""
        result = self._invoke("repair", agent, prompt, task.id)
        return result["structured_response"]

    def review(
        self,
        *,
        task: TaskSpec | None,
        requirements: str,
        architecture: str,
        security: str,
        check_results: list[dict],
        baseline_check_results: list[dict] | None,
        implementation_report: ExecutionReport | None,
        final: bool = False,
    ) -> ReviewResult:
        agent = self._build_agent("reviewer", ReviewResult)
        scope = "REVISÃO FINAL DO PROJETO" if final else f"REVISÃO DA TAREFA {task.id if task else ''}"
        prompt = f"""
{scope}

Inspecione o diff e os arquivos necessários com as ferramentas disponíveis. Avalie contra requisitos e restrições fornecidos, não contra uma arquitetura de sua preferência.

REQUISITOS:\n{requirements}

ARQUITETURA:\n{architecture}

SEGURANÇA:\n{security}

TAREFA:\n{task.model_dump_json(indent=2) if task else 'Revisão final de todas as alterações'}

RELATO DO IMPLEMENTADOR:\n{implementation_report.model_dump_json(indent=2) if implementation_report else 'N/A'}

BASELINE ANTES DAS ALTERAÇÕES:\n{json.dumps(baseline_check_results or [], ensure_ascii=False, indent=2)}

RESULTADOS DETERMINÍSTICOS ATUAIS:\n{json.dumps(check_results, ensure_ascii=False, indent=2)}

Ao avaliar regressões, diferencie problemas que já existiam no baseline de problemas introduzidos pelas alterações.

Para aprovar, não pode haver falha obrigatória conhecida, violação arquitetural relevante, risco de segurança grave conhecido ou complexidade sem justificativa que deva ser removida.
Não proponha uma arquitetura diferente. Identifique somente correções necessárias.
"""
        result = self._invoke("reviewer", agent, prompt, task.id if task else "FINAL")
        return result["structured_response"]
