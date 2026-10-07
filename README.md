# Puck

Instrumento do estudo **Benchmark de metodologias de desenvolvimento assistido por LLM**: executa,
mede e coleta a reescrita de uma fatia vertical do sistema legado
[Atena](https://github.com/Cris042/Atena) sob duas metodologias de trabalho com Claude.

| | **M1 — Direta** | **M2 — Governada** |
|---|---|---|
| Topologia | agente único, uma sessão | Arquiteto → Planner → Implementador → Revisor → Reparo |
| Modelos | Opus 5.5, `effort: medium` | strong (arquitetura, revisão), medium (planner), weak (implementação, reparo) |
| Governança | nenhuma | [`governance/m2/`](governance/m2/), inspirada no Minerva |
| Documentos | só a especificação | ADR, PRD, HLD, FDD em `docs/` |
| Gates | nenhum | revisor + reparo limitado |

Desenho: 2 techs (Laravel, Go) × 2 metodologias × 2 repetições. M1 e M2 são **pacotes**, não
variáveis isoladas. Plano e pendências: [`docs/PLANO.md`](docs/PLANO.md).

## O que é constante entre as células

- Especificação: [`spec/atena/requisitos.md`](spec/atena/requisitos.md) +
  [base técnica](spec/base-tecnica/BASE_TECNICA.md) + tarefas em [`prompts/tarefas/`](prompts/tarefas/).
- Esqueleto fixo por tech (ponto de partida do workspace) e legado no SHA fixado, exportado sem
  `.git` e acessível só para leitura (`legado_listar`, `legado_ler`, `legado_buscar`).
- Ferramentas: arquivo dentro do workspace, `git diff/status`, `run_check` dos checks configurados.
  Sem shell; `pathguard` ativo.
- Telemetria: chamada **separada**, modelo fixo, sobre o diff e o transcript de cada etapa.
- Oráculo oculto e juízes fixos.

## Instalação

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'
# juiz de outro provider (opcional):
uv pip install -p .venv -e '.[judge-openai]'

cp .env.example .env
cp config/models.example.yaml config/models.yaml
cp config/pricing.example.yaml config/pricing.yaml   # conferir preços e preencher pricing_date
```

Opus 5.5 e Sonnet 5.5 **não aceitam** `temperature`, `top_p` nem `top_k`; o controle de geração é
`effort` + `max_tokens`. O harness recusa a configuração que tentar.

```bash
atena-bench validate-config            # sem chamar LLM: modelos, parâmetros, preços
atena-bench validate-config --ping     # chama cada papel (texto + saída estruturada)
```

## Imagens do harness

```bash
atena-bench sandbox build-images      # checks Laravel/Go, oráculo, referência, usabilidade
```

## Executar

```bash
atena-bench run -e spec/atena/experiment-laravel.yaml -m m1
atena-bench run -e spec/atena/experiment-laravel.yaml -m m2
atena-bench run -e spec/atena/experiment-go.yaml      -m m1
atena-bench run -e spec/atena/experiment-go.yaml      -m m2

atena-bench evaluate runs/*                 # todos os juízes de models.yaml
atena-bench compare runs/* -o reports/campanha-01   # mediana + pontos brutos por célula
```

Execução com `valid: false` (falha de infraestrutura) é **reexecutada**, nunca pontuada.

Medições avulsas sobre um workspace (as mesmas que os checks ocultos fazem):

```bash
atena-bench sandbox check  --tech go --target test --repo runs/<id>/repo
atena-bench sandbox oracle --tech go --repo runs/<id>/repo     # caracterização HTTP
atena-bench sandbox sast | audit | dast | carga --tech go --repo runs/<id>/repo
atena-bench sandbox subir  --tech go --repo runs/<id>/repo     # gravar usabilidade
atena-bench sandbox usabilidade --tech go --repo runs/<id>/repo --roteiros runs/<id>/artifacts/usabilidade
```

Etapa 1 (antes da campanha):

```bash
atena-bench legado gerar-dourado     # executa o Atena legado e grava oracle/dataset/notas-dourado.json
atena-bench legado contaminacao      # modelos-sujeito reproduzem o Atena sem contexto?
```

## Artefatos de cada execução

```text
runs/<run-id>/
├── repo/                     # workspace (esqueleto + alterações)
├── legado/                   # Atena no SHA fixado, sem .git, somente leitura
└── artifacts/
    ├── input-snapshot/       # experimento, modelos, preços, especificação, prompts, brief.md
    ├── metrics.jsonl         # cada chamada: papel, tipo (execution|telemetry|judge), modelo,
    │                         #   timestamp, tokens (entrada/saída/cache), custo, erro
    ├── telemetry.jsonl       # telemetria validada por etapa; falha de parse é registrada
    ├── summary.json          # tech, metodologia, SHAs, parâmetros de geração, custos, checks
    ├── baseline-checks.json  hidden-baseline-checks.json  hidden-final-checks.json
    ├── changes.patch
    ├── report.md
    └── evaluations/<juiz>.json
```

## Estado

Fases A, B, C e F concluídas: harness, esqueletos, sandbox, oráculo validado e medições de
segurança, carga e usabilidade. Faltam os analyzers de qualidade (D), o RAG/MCP (E) e o piloto (G)
— ver [`docs/PLANO.md`](docs/PLANO.md). Testes com Docker: `PUCK_DOCKER_TESTS=1 pytest`.

## Documentos

- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — desenho, validade e repetibilidade
- [`docs/METRICS.md`](docs/METRICS.md) — o que é medido e de onde vem
- [`docs/SECURITY.md`](docs/SECURITY.md) — isolamento do harness
- [`docs/legado/MER_DER.md`](docs/legado/MER_DER.md) — banco do legado
