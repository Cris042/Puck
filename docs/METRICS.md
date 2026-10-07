# Métricas

## Custo e esforço — `metrics.jsonl`, `summary.json`

| Métrica | Fonte |
|---|---|
| Tokens de entrada, saída, cache lido e escrito, por chamada e papel | `UsageMetadataCallbackHandler` |
| Tipo da chamada: `execution` (metodologia), `telemetry` e `judge` (instrumento) | harness |
| Custo em USD | tokens × `pricing.yaml` (com `pricing_date`) |
| Latência por chamada, com timestamp de início (UTC) | medição externa ao modelo |
| Wall-clock da execução | harness |
| Ciclos de reparo (M2) | harness |

O custo e os tokens da metodologia (`total_cost_usd`, `total_tokens`) **excluem** telemetria e
juiz, que aparecem em `telemetry_cost_usd` e em `evaluations/<juiz>-metrics.jsonl`. Preço é
localizado pelo nome devolvido pela API, depois pelo maior prefixo configurado e por fim pelo
modelo do `models.yaml`; `run` recusa iniciar com preço ausente ou zerado.

## Telemetria — `telemetry.jsonl`

Uma entrada por etapa de escrita (agente da M1; implementação e reparo da M2), extraída por
chamada separada do diff da etapa e do transcript:

- `declared_status`: o que o executor declarou (`STATUS:`);
- por requisito: `validated` × `implemented` × `not_implemented`, com confiança `high | medium | low`;
- testes executados e falhos; regressões possíveis **só** se houver teste executado;
- violações de arquitetura, riscos, abstrações, dependências, sinais de overengineering, decisões.

`attempt` e `needs_rework` são do harness. Falha de parse ou validação vira `parse_ok: false` e entra
na taxa `telemetry_parse_failure_rate`.

## Corretude e calibração — `compare`

| Métrica | Definição |
|---|---|
| `hidden_regressions` | checks do oráculo que passavam no esqueleto e falham no final |
| `false_success` | executor declarou `success` na última etapa e o oráculo regrediu ou um check obrigatório falhou |
| contagens por check | `<check>.<contador>` no final (ex.: achados Semgrep por regra) |

## Juízes — `evaluations/<juiz>.json`

Notas 1–5 em requisitos, regressões, arquitetura, segurança, simplicidade e testes, mais achados
`blocking`/`non_blocking` com evidência. Colunas `judge.<juiz>.<dimensão>`.

## Git

Arquivos alterados, criados e removidos; linhas adicionadas e removidas; `changes.patch`.

## A implementar (fases C–F do plano)

Suíte de caracterização HTTP e dataset dourado; qualidade por linguagem (lizard, jscpd, Deptrac,
go-arch-lint, PHPStan, staticcheck, cobertura); usabilidade (Playwright, KLM); carga (k6);
segurança (Semgrep, ZAP, auditoria de dependências); catálogo de falhas por tipo.
