# Plano de preparação do Puck para o protocolo experimental

Documento vivo até o pré-registro; depois disso, mudanças só com registro no histórico.
Protocolo de referência: *Benchmark de metodologias de desenvolvimento assistido por LLM*
(2 techs × 2 metodologias × 2 repetições).

## 1. Decisões tomadas

| # | Decisão | Data |
|---|---|---|
| D-01 | Remover a trilha antiga (modernização in-place, comparação OpenAI × Anthropic). Puck vira instrumento exclusivo deste protocolo. | 2026-10-07 |
| D-02 | Cada célula parte de um **esqueleto mínimo fixo** por tech (Laravel, Go), idêntico em M1 e M2. | 2026-10-07 |
| D-03 | **Dois juízes**: Claude calibrado contra 30 casos rotulados + juiz de outro provider; reportar concordância. | 2026-10-07 |
| D-04 | O banco legado é refatorado como parte da reescrita: MER/DER em [`docs/legado/MER_DER.md`](legado/MER_DER.md), tarefa em [`prompts/tarefas/refatoracao-banco.md`](../prompts/tarefas/refatoracao-banco.md). | 2026-10-07 |
| D-05 | Base técnica comum às 8 células em [`spec/base-tecnica/BASE_TECNICA.md`](../spec/base-tecnica/BASE_TECNICA.md) (Argon2id + pepper, contrato de camadas, cobertura, ferramentas). | 2026-10-07 |

## 2. Achados que alteram o protocolo

1. **Parâmetros de amostragem não são controláveis.** Claude Opus 5.5 e Sonnet 5.5 rejeitam
   `temperature`, `top_p` e `top_k` (HTTP 400) e não permitem desligar o raciocínio; o controle
   disponível é `effort` (`low`…`max`) e `max_tokens`. Haiku 4.5 aceita amostragem, mas não
   `effort`. **Ajuste no protocolo (seção 3):** substituir "temperatura/top-p/top-k baixos" por
   "`effort` e `max_tokens` declarados por papel; amostragem fixada pelo provider e não
   controlável" — e listar em ameaças à validade.
2. **O dump MariaDB 2020 não é o banco do commit fixado.** O código `ac48dc5` (2024) usa outro
   modelo (`alunos2`, `professo2`, `secretaria2`, `diciplina`, `notas` com chave composta textual).
   O MER/DER segue o código; o dump fica só como histórico, sem os dados pessoais.
3. **Contaminação reforçada.** O repositório público do Atena contém, depois do SHA fixado, uma
   reescrita em Java e um schema reconstruído. Os modelos podem tê-la visto. Verificação de
   contaminação (etapa 1) deve incluir prompts sem contexto pedindo essas estruturas.
4. **Divergência no schema reconstruído.** `horario.cod_curos` no código × `cod_curso` no
   `infra/legado/schema.sql` do Atena: o schema reconstruído quebra o código fixado nessa tabela.
5. **O `single` atual não é agente único** — rodava o pipeline de 5 papéis com o mesmo modelo. A M1
   precisa de loop próprio.
6. **A telemetria contaminava a M1**: o executor preenchia o relatório estruturado na mesma
   chamada, e `prompts/common.md` aplicava regras de governança a todos os papéis.

## 3. Lacunas e fases

| Fase | Entrega | Critério de pronto | Etapa do protocolo |
|---|---|---|---|
| **A. Reorientação do harness** ✅ 2026-10-07 | eixos tech × metodologia; M1 agente único; M2 hierárquica com documentos; telemetria em chamada separada e validada; prompts na estrutura de 8 seções; `models.yaml` só Claude com `effort`; SHAs dos 4 repositórios no `summary.json`; mediana + pontos brutos; dois juízes | testes do harness passam; dry-run com modelos falsos produz todos os artefatos | 2, 3, 5 |
| **B. Alvos executáveis** ✅ 2026-10-07 | esqueletos Laravel e Go conforme a base técnica; compose com PostgreSQL; etapa do harness que sobe a app e espera `/saude` | esqueleto sobe duas vezes do zero com o mesmo resultado | 1 |
| **C. Oráculo** ✅ 2026-10-07 | Atena legado rodando (PHP + banco do MER); contrato HTTP (OpenAPI); suíte de caracterização HTTP independente de stack; dataset dourado; seed sintético | quebrar regra de propósito e o oráculo acusar; baseline reproduzível duas vezes | 1 |
| **D. Analyzers** | Deptrac / go-arch-lint com o contrato; lizard, jscpd, cobertura, PHPStan, staticcheck; delta base → head | métricas reconstruídas só pelos artefatos | 3 |
| **E. RAG + MCP** | extração de regras (Pydantic) → dataset dourado; índice pgvector híbrido + rerank; `buscar_contexto_legado`; servidor MCP com `pathguard`; avaliação de 30 perguntas | delta vetorial × híbrida medido; índice congelado | 4, 5 |
| **F. Usabilidade, carga, segurança** ✅ 2026-10-07 | Playwright (KLM), k6, ZAP baseline, Semgrep por linguagem | cenários idênticos rodando contra as duas stacks | 6 |
| **G. Piloto e campanha** | calibração dos juízes; ruído de base; 8 execuções; análise | protocolo, seção 10, etapas 6 e 7 | 6, 7 |

## 4. Estado da fase A

Concluída. Pontos que só a execução real confirma:

- saída estruturada nativa (`ProviderStrategy` / `json_schema`) nos modelos 5.x: verificar com
  `atena-bench validate-config --ping` antes do dry-run real;
- teto `max_tokens: 16000` por resposta (chamadas sem streaming): avaliar no piloto se trunca;
- juiz externo (P-06) e `pricing_date` ainda em aberto, e `validate-config` recusa enquanto isso.

Coberto por teste: roteamento M1/M2, teto de reparo, telemetria (`attempt`/`needs_rework` do
harness, falha de parse como métrica, regressão sem teste rejeitada), governança só na M2, prompts
nas 8 seções, patch do juiz sem `docs/`, mediana e pontos brutos, falso sucesso, e uma execução seca
ponta a ponta com repositórios git locais.

## 4.1 Estado das fases B, C e F

- **B:** esqueletos `scaffolds/laravel` (PHP 8.5.11, Laravel 13) e `scaffolds/go` (Go 1.27.1)
  passam em lint, arch, test e coverage no sandbox, sobem e respondem `/saude`; SAST e auditoria
  limpos. Congelados por SHA de conteúdo. O contrato de camadas acusa violações plantadas nas duas
  stacks.
- **C:** dataset dourado gerado executando o legado (148 casos, reproduzível byte a byte);
  contrato HTTP; oráculo com 175 testes; a referência passa em tudo e as 6 mutações são acusadas.
  Etapa 1 cumprida, exceto a **verificação de contaminação**, que exige rodar
  `atena-bench legado contaminacao` com a chave da API.
- **F:** SAST (regras validadas contra amostras boas e ruins), dependências, ZAP, k6 (aquecimento
  + 3 rodadas, mediana) e usabilidade (reexecução de roteiros gravados + KLM), todos verificados
  contra a referência pelo sandbox.
- **Falta:** D (analyzers de qualidade), E (RAG + MCP), G (piloto e campanha); gravações de
  usabilidade são manuais por célula.

## 5. Decisões pendentes (precisam do seu aval)

| # | Questão | Proposta |
|---|---|---|
| P-01 | Contrato HTTP: JSON fixo (oráculo) + UI renderizada no servidor e livre (usabilidade) | aceitar (base técnica, seção 5) |
| P-02 | Regra de faltas do legado (reprova só acima de 75% e só se média < 60) | **preservar** e caracterizar; corrigir é outra campanha |
| P-03 | Login do sistema novo mantém `email + matrícula + senha` do legado? | manter, para o oráculo de caracterização valer |
| P-04 | Senhas md5 legadas: rehash no primeiro login | aceitar (base técnica, 3.1) |
| P-05 | Modelo de embeddings do RAG (Anthropic não oferece) | modelo aberto local, declarado como instrumento |
| P-06 | Juiz de outro provider: qual modelo | definir antes do piloto |
| P-07 | Base técnica entregue também à M1 | aceitar e declarar como ameaça à validade |
| P-08 | Tiers da M2: strong = Opus 5.5, medium = Sonnet 5.5, weak = Haiku 4.5 | confirmar |
| P-09 | Prazo de lançamento (RF-05) bloqueia lançamento fora dele? O legado só marca `atrasada_*`; o efeito não foi caracterizado | contrato aceita definir o prazo, mas não exige bloqueio; oráculo não testa |
| P-10 | Tipo real das colunas de notas em 2024 (texto × INT, que arredonda a média) | dourado assume texto (valor calculado pelo PHP); confirmar com um dump do banco de 2024, se existir |
