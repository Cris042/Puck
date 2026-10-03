# Metodologia

## Pergunta do experimento
Comparar estratégias de uso de LLMs na evolução de um sistema legado, observando qualidade de engenharia, custo e eficiência.

## Variáveis

| Variável | Valores | Onde se define |
|---|---|---|
| Provider | `openai`, `anthropic` | `--provider` |
| Estratégia | `single`, `hierarchical` | `--strategy` |
| Governança | `none`, `minerva-benchmark` | `governance_file` no experimento |

Todo o resto fica constante: commit base, requisitos, arquitetura, tarefas, prompts, checks,
limite de correções, limite de passos por agente, tabela de preços e versão das ferramentas.

### `single`
O tier `strong` executa arquitetura, planejamento, implementação, correção e revisão.

### `hierarchical`
- `strong`: arquitetura e revisão;
- `medium`: planejamento/orquestração;
- `weak`: implementação e correções.

### Governança
`governance/minerva-benchmark.md` é um recorte congelado das regras do Minerva (papéis,
triagem por severidade, `⚠️ DÍVIDA`, `❓ LACUNA`, ADR para decisão estrutural). Comparar
`experiment-fixed.yaml` com `experiment-fixed-minerva.yaml` isola o efeito da governança.

## Trilhas

- **Tarefas fixas (`tasks_file`) — use para comparar.** Todas as execuções implementam as mesmas
  tarefas; o planner não é chamado. Taxa de aprovação, custo por tarefa e regressões passam a ser
  comparáveis.
- **Aberta (planner decide) — use para observar.** Cada execução escolhe tarefas diferentes, então
  "tarefas aprovadas" não é comparável entre execuções.

## Três camadas de evidência

1. **Checks visíveis** (`checks_file`): o agente pode rodá-los e o revisor os recebe. Funcionam
   como o CI do projeto.
2. **Checks ocultos** (`hidden_checks_file`): rodam só no baseline e no final, fora do alcance das
   ferramentas dos agentes. São o oráculo: medem sem ensinar, e não podem ser "otimizados" pelo
   modelo. A barreira é de filesystem, não de prompt.
3. **Juiz independente** (`atena-bench evaluate`): o revisor dentro do workflow é o modelo do
   próprio provider avaliado; ele serve ao ciclo de correção, mas não para comparar providers.
   O juiz é fixo para a campanha inteira, não sabe provider/estratégia/modelo e pontua 1–5 em seis
   dimensões. Para reduzir viés de autopreferência, use um juiz de provider diferente dos
   avaliados ou dois juízes de providers distintos e reporte ambos.

## Validade de uma execução

- Falha de infraestrutura (rede, rate limit, autenticação, bug do harness) marca `valid: false`.
  A execução é repetida com novo run ID e não entra nas médias.
- Estourar `max_agent_steps` ou devolver saída estruturada inválida conta **contra o modelo**:
  a tarefa fica reprovada e a execução segue para a próxima tarefa.
- Use SHA em `base_ref`; o workspace registra o commit efetivamente usado (`base_commit`).

## Repetições
Pelo menos 3 execuções válidas de cada combinação provider × estratégia × governança. Agregue com
`atena-bench compare runs/*` (média ± desvio padrão). Com 3 repetições, diferenças menores que o
desvio padrão não sustentam conclusão.

## Pré-registro
Antes da primeira execução da campanha, registre: hipóteses, métricas primárias, pesos e critério
de leitura. Escolher a métrica depois de ver o resultado invalida a comparação.

## Interpretação
O benchmark mede desempenho **neste cenário**. Ele não demonstra superioridade universal de um modelo. Sistemas financeiros, críticos, sociais, internos ou experimentais possuem riscos e prioridades diferentes, portanto os trade-offs mudam conforme o domínio.
