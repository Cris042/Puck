# Métricas

## Coletadas pelo runtime
- tokens de entrada;
- tokens de saída;
- tokens totais;
- cache quando reportado pelo provider;
- tempo por papel/etapa;
- custo calculado pelo `pricing.yaml`;
- número de chamadas;
- número de ciclos de correção;
- erros por etapa, classificados em `agent_step_limit`, `invalid_output` e `infra`.

A LLM não estima essas métricas. O preço é localizado pelo nome devolvido pela API, depois pelo
maior prefixo configurado (snapshots datados) e por fim pelo modelo do `models.yaml`. Modelos sem
preço aparecem em `unpriced_models`; `run` recusa iniciar com preço ausente ou zerado, salvo
`--allow-unpriced`.

## Coletadas por Git
- arquivos alterados/criados/removidos;
- linhas adicionadas/removidas;
- patch final.

## Checks determinísticos
Status `passed`/`failed`/`unavailable`/`timeout` e, quando há `parser`, contagens comparáveis
entre baseline e final (`semgrep_json` por regra, `phpunit` testes/falhas, `line_count`).

Configuráveis em `checks.yaml`, por exemplo:
- PHP lint;
- PHPUnit;
- PHPStan/Psalm;
- Deptrac;
- Semgrep;
- Composer Audit.

## Oráculo oculto
Checks em `hidden_checks_file`, executados só pelo harness. No Atena: regras Semgrep locais de
segurança e arquitetura e endpoints AJAX sem sessão. Métrica: contagem baseline → final por
regra e checks que regrediram.

## Juiz independente (`atena-bench evaluate`)
Notas 1–5 em requisitos, regressões, arquitetura, segurança, simplicidade e testes, mais achados
`blocking`/`non_blocking` com evidência. Gravado em `artifacts/evaluation.json`.

## Avaliação estruturada da LLM (dentro do workflow)
- requisitos e regressões possíveis;
- aderência arquitetural;
- segurança;
- overengineering;
- justificativas de abstrações/dependências;
- retrabalho.

## Agregação
`atena-bench compare runs/* -o reports/campanha` gera `.md`, `.runs.csv` e `.groups.csv` com
média ± desvio padrão por provider × estratégia × governança, excluindo execuções inválidas.

## Métricas derivadas recomendadas
- custo / tarefa aprovada;
- tokens / tarefa aprovada;
- tempo / tarefa aprovada;
- ciclos de correção / tarefa;
- linhas adicionadas / requisito entregue (usar apenas como sinal, não como qualidade isolada);
- abstrações sem justificativa / abstrações criadas.
