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

## Oráculo oculto — `config/hidden-checks.yaml`

Rodam no esqueleto e no final, pelo sandbox, fora do alcance dos agentes. Todas emitem
`PUCK_METRIC <nome> <inteiro>`, que viram contagens comparáveis (`<check>.<métrica>`).

| Check | Métricas | Fonte |
|---|---|---|
| `caracterizacao` | `oraculo_<area>_total` / `_falhas` (saude, autenticacao, autorizacao, cadastros, regra_notas) | `oracle/suite` + dataset dourado do legado executado |
| `sast` | `sast_<regra>`, `sast_total`, `sast_erros_varredura` | Semgrep 1.179.0, `config/semgrep/<linguagem>.yml` |
| `dependencias` | `deps_vulnerabilidades`, `deps_alcancaveis` | `composer audit` / `govulncheck` (base consultada na data da execução) |
| `dast` | `dast_alto`, `dast_medio`, `dast_baixo`, `dast_info` | ZAP baseline 2.17.0 |
| `carga` | `carga_{leitura,escrita}_{p50,p95,max}_ms`, `_falhas_permil`, `carga_req_por_s_x100` (mediana e `_rN` por rodada) | k6 2.3.0, `oracle/carga/cenario.js` |

Checks do projeto (`config/checks.<tech>.yaml`): `lint`, `arch` (contrato de camadas), `test` e
`coverage` (`coverage_permille`, `coverage_core_permille` para domínio + regra).

## Usabilidade — `atena-bench sandbox usabilidade`

Por tarefa (`usab_tarefa_N_*`): conclusão verificada pela API, telas e navegações na reexecução, e
KLM do roteiro gravado (`klm_ms`, operadores K/P/B/H/M, campos, cliques). Protocolo do avaliador:
[`oracle/usabilidade/TAREFAS.md`](../oracle/usabilidade/TAREFAS.md).

## Validade do próprio oráculo

`tests/test_oraculo.py`: o dataset dourado é íntegro (hash) e cobre as quatro situações; a regra
escrita reproduz todos os resultados do legado; a implementação de referência passa em tudo; e
cada uma das seis mutações deliberadas é acusada na área certa.

## A implementar

Analyzers de qualidade por linguagem (fase D: lizard, jscpd, PHPMetrics, acoplamento) e catálogo
de falhas por tipo.
