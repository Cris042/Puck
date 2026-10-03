# Atena LLM Benchmark

Harness experimental para comparar estratégias de uso de LLMs em engenharia de software usando **LangChain**, **LangGraph** e **LangSmith**.

O primeiro cenário de referência é o [Atena](https://github.com/Cris042/Atena), um sistema acadêmico legado em PHP. O harness, porém, foi criado para receber outros repositórios e outras regras de arquitetura.

## Objetivo

Comparar duas metodologias mantendo o máximo possível das demais variáveis constantes:

- **single**: o modelo `strong` executa arquitetura, planejamento, implementação, correção e revisão;
- **hierarchical**: `strong` cuida de arquitetura/revisão, `medium` de planejamento/orquestração e `weak` de implementação/correção.

O benchmark registra custo e eficiência, mas também avalia:

- aderência a requisitos;
- aderência à arquitetura;
- segurança;
- regressões, comparando checks com um baseline anterior às alterações;
- retrabalho;
- complexidade e overengineering;
- alterações no código.

> O benchmark não busca declarar um modelo universalmente melhor. Software é um sistema vivo: cada domínio tem riscos, restrições e prioridades diferentes. Um sistema financeiro ou crítico e uma rede social, por exemplo, podem exigir trade-offs completamente diferentes.

## Arquitetura do harness

```text
Experiment YAML
      |
      v
Workspace isolado (clone)
      |
      v
LangGraph
  architect ------ strong
      |
  planner -------- strong(single) / medium(hierarchical)
      |
  implement ------ strong(single) / weak(hierarchical)
      |
  deterministic checks
      |
  reviewer ------- strong
      |              |
      | reprovado    | aprovado
      v              v
  repair --------> próxima tarefa
      |
      +---- loop limitado
      |
      v
final review
      |
      v
JSON + metrics.jsonl + patch + relatório LinkedIn
```

## Segurança do harness

A LLM não recebe shell arbitrário. O agente pode:

- listar, ler, buscar, criar, substituir e excluir arquivos dentro do workspace;
- consultar `git diff/status`;
- executar **somente** checks definidos previamente em `checks.yaml`.

Veja [docs/SECURITY.md](docs/SECURITY.md).

## Requisitos

- Python 3.11+;
- Git;
- Docker (checks do Atena rodam em container sem rede);
- chaves das APIs que serão usadas.

Imagens dos checks do Atena:

```bash
docker build -t atena-checks:php7.3 docker/atena-checks
docker pull semgrep/semgrep:1.140.0
```

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
```

Crie as configurações locais:

```bash
cp .env.example .env
cp config/models.example.yaml config/models.yaml
cp config/pricing.example.yaml config/pricing.yaml
```

Edite `config/models.yaml` com os **IDs reais de API disponíveis na sua conta**. Os nomes de produto/tier usados em interfaces de chat não necessariamente são IDs de API.

Edite `config/pricing.yaml` com os preços vigentes no dia do experimento. O harness não embute preço fixo porque preço de modelo muda ao longo do tempo.

## LangSmith

No `.env`:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=atena-llm-benchmark
```

O LangSmith recebe tags/metadata como provider, estratégia, papel, tier, run ID e task ID. A pasta `runs/` mantém também uma cópia local dos dados essenciais.

## Validar configuração

```bash
atena-bench validate-config \
  --models config/models.yaml \
  --pricing config/pricing.yaml

# Também faz uma chamada mínima a cada modelo (valida ID, chave e parâmetros):
atena-bench validate-config --ping
```

`validate-config` e `run` falham se algum modelo configurado não tiver preço ou tiver preço zerado.

## Experimentos do Atena

| Arquivo | Uso |
|---|---|
| `examples/atena/experiment-fixed.yaml` | **Comparação.** Tarefas fixas de `tasks.yaml`, sem governança extra |
| `examples/atena/experiment-fixed-minerva.yaml` | Mesmas tarefas com o perfil de governança Minerva |
| `examples/atena/experiment.yaml` | Trilha aberta: o planner escolhe as tarefas (observação, não comparação) |

Todos fixam o commit `ac48dc5` do Atena. Antes de rodar, leia
[docs/ATENA_BASELINE.md](docs/ATENA_BASELINE.md): ele lista o que foi medido no baseline e os
documentos que ainda faltam.

## Executar

### OpenAI — modelo forte em todo o workflow

```bash
atena-bench run \
  --experiment examples/atena/experiment-fixed.yaml \
  --provider openai \
  --strategy single \
  --models config/models.yaml \
  --pricing config/pricing.yaml
```

### OpenAI — hierárquico

```bash
atena-bench run --provider openai --strategy hierarchical
```

### Anthropic — modelo forte em todo o workflow

```bash
atena-bench run --provider anthropic --strategy single
```

### Anthropic — hierárquico

```bash
atena-bench run --provider anthropic --strategy hierarchical
```

`--provider claude` também é aceito como alias de `anthropic`.

### Avaliar e comparar

```bash
# Juiz fixo (seção `judge:` do models.yaml), cego a provider e estratégia:
atena-bench evaluate runs/*

# Média ± desvio padrão por provider × estratégia × governança:
atena-bench compare runs/* -o reports/campanha-01
```

## Artefatos de cada execução

```text
runs/<run-id>/
├── repo/                     # clone isolado alterado pelas LLMs
└── artifacts/
    ├── input-snapshot/              # specs, tarefas, governança, checks, prompts, modelos, preços
    ├── baseline-checks.json         # checks visíveis antes das alterações
    ├── hidden-baseline-checks.json  # oráculo antes das alterações
    ├── hidden-final-checks.json     # oráculo depois das alterações
    ├── metrics.jsonl                # cada chamada/role: tokens, tempo, custo, erro
    ├── summary.json                 # resumo machine-readable (validade, erros, tarefas)
    ├── changes.patch                # alterações geradas (inclui arquivos novos e removidos)
    ├── evaluation.json              # após `evaluate`: notas do juiz independente
    └── linkedin-report.md           # relatório curto para publicação
```

## Configuração de modelos

Exemplo:

```yaml
providers:
  openai:
    strong:
      model: "SEU_MODELO_FORTE"
      reasoning_effort: medium
    medium:
      model: "SEU_MODELO_INTERMEDIARIO"
      reasoning_effort: medium
    weak:
      model: "SEU_MODELO_ECONOMICO"

  anthropic:
    strong:
      model: "SEU_CLAUDE_FORTE"
      reasoning_effort: medium
    medium:
      model: "SEU_CLAUDE_INTERMEDIARIO"
    weak:
      model: "SEU_CLAUDE_ECONOMICO"
```

Parâmetros específicos podem ser passados em `extra`:

```yaml
strong:
  model: "..."
  extra:
    alguma_opcao_do_provider: true
```

## Métricas

Tokens são coletados por `UsageMetadataCallbackHandler`, e latência é medida externamente à resposta do modelo. O custo é calculado a partir do `pricing.yaml`.

A LLM registra somente informações que dependem da execução de engenharia, como:

- requisito tratado/não tratado;
- possíveis regressões;
- violações arquiteturais;
- abstrações e dependências criadas;
- problemas/riscos de segurança;
- indícios de overengineering;
- retrabalho e decisões/trade-offs.

Detalhes: [docs/METRICS.md](docs/METRICS.md).

## Checks determinísticos

- `config/checks.atena.yaml` — **visíveis** aos agentes: PHP lint (7.3), PHPUnit 9.6, PHPStan 1.12.
- `config/hidden-checks.atena.yaml` — **ocultos** (oráculo): regras Semgrep locais de segurança e
  arquitetura (`config/semgrep/`) e endpoints AJAX sem sessão.
- `config/checks.example.yaml` — exemplo genérico com ferramentas do host.

`exit 0` é sucesso; códigos em `unavailable_exit_codes` (padrão `127`) marcam `unavailable`.
Comandos aceitam `{repo_dir}` e `{config_dir}`. Com `parser`, o check também produz contagens
comparáveis entre baseline e final.

## Repetibilidade

Para uma comparação minimamente útil:

1. fixe o mesmo commit do projeto (SHA em `base_ref`);
2. congele requisitos, arquitetura, tarefas, governança, prompts e checks;
3. use a mesma tabela de preços/data;
4. use o mesmo limite de correções;
5. execute pelo menos 3 repetições de cada combinação;
6. não reutilize o workspace de uma execução anterior;
7. repita execuções marcadas como inválidas (`valid: false`) em vez de pontuá-las.

Veja [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Estrutura

```text
src/atena_benchmark/
├── agents.py        # agentes/papéis
├── analysis.py      # deltas baseline × final e agregação de repetições
├── checks.py        # validação determinística e parsers de contagem
├── cli.py           # CLI
├── config.py        # schemas YAML
├── costing.py       # cálculo de custo
├── evaluation.py    # juiz independente pós-execução
├── git_stats.py     # estatísticas de alteração
├── graph.py         # workflow LangGraph
├── metrics.py       # tokens/latência/custo
├── models.py        # roteamento strong/medium/weak
├── pathguard.py     # proteção de filesystem
├── prompts.py       # carregamento dos prompts
├── repo_tools.py    # ferramentas expostas às LLMs
├── reporting.py     # relatório LinkedIn
├── runner.py        # orquestração da execução
└── workspace.py     # clone isolado
```

## Sobre os resultados

Não interprete o relatório como ranking universal. A estratégia mais barata pode ser inadequada para um cenário crítico; uma estratégia mais cara pode ser desperdício para uma mudança simples. O foco é observar **trade-offs dentro do contexto medido**.
