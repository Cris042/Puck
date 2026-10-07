# Metodologia

## Pergunta

Esta forma de trabalhar com LLM (M2, governada) rende mais que aquela (M1, direta) na reescrita de
uma fatia vertical de um sistema legado — em custo, tempo, corretude, qualidade, usabilidade,
desempenho e segurança? **Não** responde qual componente causou a diferença: M1 e M2 diferem em
vários fatores ao mesmo tempo (topologia, modelos, governança, documentos, gates).

## Desenho

| Fator | Níveis | Onde se define |
|---|---|---|
| Tech | `laravel`, `go` | `spec/atena/experiment-<tech>.yaml` |
| Metodologia | `m1`, `m2` | `atena-bench run -m` |
| Repetição | 2 por célula | execuções independentes |

Análise principal: M1 × M2 **dentro** de cada tech.

## Constantes

SHA do esqueleto, do legado e das referências (registrados em `summary.json`); especificação, base
técnica e tarefas (mesmo `brief.md` para M1 e M2); ferramentas dos agentes; contexto do legado;
prompts de telemetria e do juiz; checks visíveis e ocultos; limites de passos e de reparo; tabela
de preços com data; parâmetros de geração por papel.

**Parâmetros de geração.** Opus 5.5 e Sonnet 5.5 não aceitam `temperature`, `top_p` nem `top_k` e
não desligam o raciocínio. O controle é `effort` e `max_tokens`, declarados por papel e copiados
para o `summary.json`. A amostragem é fixada pelo provider e não é controlável: ameaça à validade.

## Tratamentos

- **M1:** um agente (`prompts/m1/agente.md`), uma sessão de até `m1_max_agent_steps` passos. Não
  recebe governança, documentos de processo, revisor nem reparo.
- **M2:** grafo de papéis (`prompts/m2/`), governança de `governance/m2/` anexada a todos eles,
  documentos ADR/PRD/HLD/FDD gravados pelo arquiteto, revisão por tarefa e reparo limitado a
  `max_repair_cycles`.

## Evidência, do mais ao menos objetivo

1. **Oráculo oculto** (`hidden_checks_file`): roda no esqueleto e no final, fora do alcance dos
   agentes. Mede sem ensinar.
2. **Checks do projeto** (`checks_file`): os agentes podem rodá-los; o harness registra o resultado
   no esqueleto e no final.
3. **Juízes** (`atena-bench evaluate`): fixos para a campanha, cegos à metodologia (documentos em
   `docs/` retirados do patch). Um Claude calibrado contra 30 casos rotulados e um de outro
   provider; reportar a concordância.
4. **Telemetria**: o que o executor declarou e o que o diff mostra. Entra na métrica de
   **calibração** (falso sucesso), nunca no índice de qualidade.

## Validade de uma execução

- Falha de infraestrutura (rede, rate limit, autenticação, bug do harness) marca `valid: false`: a
  execução é repetida com novo run ID e não entra na análise.
- Estourar passos ou devolver saída estruturada inválida conta **contra a metodologia**.
- Workspace nunca é reutilizado.

## Análise

`atena-bench compare` reporta, por tech × metodologia, a **mediana e todos os pontos**. Com 2
repetições por célula não há teste de significância; diferenças menores que a dispersão entre
repetições não sustentam conclusão.

## Pré-registro

Antes da primeira execução: matriz, hipóteses, métricas primárias e pesos do índice de qualidade em
documento versionado. Escolher a métrica depois de ver o resultado invalida a comparação.
