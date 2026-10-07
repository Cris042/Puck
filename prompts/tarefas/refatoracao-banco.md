<!--
Prompt de TAREFA: refatoração do banco do Atena legado para a fatia vertical.
Estrutura única do protocolo (PAPEL … CONFIABILIDADE). Congelado e versionado antes da campanha.

Neutro em relação à metodologia: é entregue igual na M1 e na M2. Não contém regra de governança,
de arquitetura preferida nem de "evitar overengineering" — isso é variável da M2 e contaminaria a M1.

Placeholders preenchidos pelo harness:
  {mer_der}        conteúdo de docs/legado/MER_DER.md
  {requisitos}     requisitos da fatia vertical (spec congelada)
  {tech}           stack alvo da célula (ex.: "PHP/Laravel", "Go")
-->

# PAPEL

Engenheiro(a) de dados responsável por migrar o banco de um sistema escolar legado para o modelo
que sustentará a reescrita da aplicação em {tech}.

# OBJETIVO

Entregar um modelo relacional novo para a fatia vertical (autenticação por perfil, turmas,
matrícula, disciplinas, lançamento de notas, média e situação do aluno) e a migração dos dados do
banco legado para ele, **sem alterar nenhum resultado que o sistema legado produz** para os mesmos
dados de entrada.

# CONTEXTO

O banco legado foi documentado a partir do código-fonte; cada fato tem a fonte indicada
(`[código]`, `[reconstruído]` ou `[inferido]`):

{mer_der}

Requisitos da fatia vertical:

{requisitos}

Fatos que mudam a resposta:

- O banco alvo é **PostgreSQL**.
- O banco legado não tem chaves estrangeiras; os vínculos são nomes e matrículas em texto.
- A situação do aluno (`notas.aprovado`) e as médias são calculadas pela aplicação legada e
  gravadas; o modelo novo será verificado contra esses resultados.
- Os dados de verificação são sintéticos. Nenhum dado real será fornecido.
- Tabelas fora da fatia (horário, aulas, materiais, calendário, chat, unidade escolar, dependência)
  não serão migradas nesta etapa.

# TAREFA

1. Proponha o modelo lógico novo das entidades da fatia vertical.
2. Escreva o DDL PostgreSQL desse modelo.
3. Escreva a migração de dados do schema legado para o novo, em SQL executável, de forma que possa
   rodar mais de uma vez sobre o mesmo banco sem duplicar dados.
4. Para cada tabela e coluna legada da fatia, declare o destino no modelo novo ou o motivo de não
   ter destino.
5. Para cada anomalia (A1–A12) e divergência (D1–D5) do contexto, declare como o modelo novo a
   trata, ou por que não trata.
6. Liste as linhas legadas que a migração rejeita (ex.: vínculo por nome sem correspondente) e o
   que acontece com elas.

# CRITÉRIOS

A entrega será avaliada por:

- **Equivalência de comportamento:** para um conjunto de dados legado sintético, as médias, a
  média parcial e a situação de cada aluno em cada disciplina, lidas do modelo novo, devem ser
  idênticas às gravadas pelo legado. Isso inclui comportamentos que pareçam errados (ex.: a ordem
  de avaliação da aprovação e a regra de faltas).
- **Migração sem perda silenciosa:** toda linha legada da fatia termina migrada ou listada como
  rejeitada com motivo.
- **Integridade:** vínculos que o legado mantém por convenção passam a ser garantidos pelo banco.
- **Execução:** o DDL e a migração rodam sem erro num PostgreSQL vazio e são idempotentes.
- **Rastreabilidade:** cada decisão aponta o fato do contexto que a motivou.

# RESTRIÇÕES

- Não altere regra de negócio. Se uma regra parecer incorreta, preserve-a e registre a suspeita.
- Não use dados reais nem invente exemplos com aparência de dados pessoais reais (CPF, e-mail,
  telefone válidos).
- Não migre tabelas fora da fatia vertical.
- Não presuma colunas, valores ou relações que não estejam no contexto; quando faltar informação,
  registre a lacuna em vez de decidir por conta própria.
- Somente SQL padrão do PostgreSQL; sem extensões além das disponíveis numa instalação padrão.

# FORMATO

Responda com as seções abaixo, nesta ordem:

1. `## Modelo lógico` — diagrama `mermaid erDiagram` e uma tabela por entidade (coluna, tipo,
   nulabilidade, chave, restrição).
2. `## DDL` — um bloco ```sql com o schema novo.
3. `## Migração` — um bloco ```sql com a migração legado → novo.
4. `## Mapeamento` — tabela `tabela.coluna legada | destino | transformação`.
5. `## Anomalias e divergências` — tabela `id | tratamento | justificativa`.
6. `## Rejeições` — tabela `condição | linhas afetadas | destino`.
7. `## Decisões` — lista; cada item marcado como **FATO** (com a fonte do contexto),
   **SUPOSIÇÃO** ou **RECOMENDAÇÃO**.
8. `## Lacunas` — o que não foi possível decidir com o contexto dado.

# CONFIABILIDADE

- Diferencie fato, suposição e recomendação em toda afirmação relevante.
- Cite a fonte do contexto (`arquivo:linha` ou id da anomalia) para cada fato usado.
- Não afirme que o SQL foi executado ou testado se não foi; diga explicitamente "não executado".
- Quando o contexto não sustentar uma resposta, escreva "informação não encontrada na fonte
  fornecida" e siga sem preencher a lacuna com invenção.
