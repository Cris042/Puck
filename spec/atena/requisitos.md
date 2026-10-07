<!--
RASCUNHO para validação do autor — congela na etapa 2 do protocolo.
Requisitos da fatia vertical, idênticos para as 8 células. Objetivos, não telas: a usabilidade mede
design (protocolo, 4.4). Regras de negócio apontam a fonte no legado; o oráculo oculto as verifica.
-->

# Reescrita da fatia vertical do Atena

Sistema escolar com três perfis — **aluno**, **professor** e **secretário** — que reescreve, numa
nova base técnica, o fluxo de notas do sistema legado Atena: matrícula em turma, lançamento de notas
por bimestre, cálculo de média e decisão de aprovação, com autenticação e autorização por perfil.

## Requisitos funcionais

| Id | Requisito | Fonte no legado |
|---|---|---|
| RF-01 | Usuário entra informando e-mail, matrícula e senha; o sistema identifica o perfil. Credenciais inválidas recebem uma resposta única, sem dizer qual campo errou. | `Models/HomeMolde.php:13-71` |
| RF-02 | Secretário cadastra aluno, professor, curso, série, ano letivo e turma (ano + curso + série). | `Models/ajax/Cadastro*.php`, `Models/ajax/Gestaotumas.php` |
| RF-03 | Secretário cadastra disciplina numa turma, com professor responsável e carga horária. | `Models/MainMolde.php:380-400` |
| RF-04 | Secretário matricula alunos numa turma; o aluno passa a constar em todas as disciplinas dela. | `Models/MainMolde.php:425-440` |
| RF-05 | Secretário define o prazo de lançamento de cada bimestre. | `Models/MainMolde.php:310-327` |
| RF-06 | Professor lança, para cada aluno de uma disciplina sua, a nota e a recuperação de cada um dos 4 bimestres. | `Models/ajax/CadastroNotas.php` |
| RF-07 | Professor registra faltas por aluno, disciplina e data. | `Models/ajax/EnviarAlaiacao.php:890-900` |
| RF-08 | O sistema calcula nota efetiva, média, média parcial e situação de cada aluno em cada disciplina, **exatamente** pela regra do legado (seção "Regra de notas"). | `Models/ajax/CadastroNotas.php:55-198` |
| RF-09 | Aluno consulta suas notas, médias e situação por disciplina (boletim). | `Views/pages/boletim-aluno.php` |
| RF-10 | Professor e secretário consultam o boletim de uma turma. | `Views/pages/boletim.php`, `Views/pages/boletim-adm.php` |
| RF-11 | O banco legado da fatia é migrado para o modelo novo sem perda silenciosa (tarefa de refatoração do banco). | `docs/legado/MER_DER.md` |

## Regra de notas (preservar, inclusive o que parece errado)

1. Nota acima de 100 vira 100; recuperação acima de 60 vira 60.
2. Nota efetiva do bimestre = recuperação, se a nota for menor que 60 **e** a recuperação maior que a
   nota; senão, a nota.
3. Média = soma das 4 notas efetivas ÷ 4. Média parcial = soma das notas efetivas lançadas ÷ número de
   bimestres lançados.
4. Situação, avaliada nesta ordem:
   1. **aprovado** se média ≥ 60 e os 4 bimestres foram lançados;
   2. senão, **reprovado por faltas** se faltas × 55 min > 75% da carga horária;
   3. senão, **reprovado** se média < 60 e os 4 bimestres foram lançados;
   4. senão, **cursando**.

A ordem faz um aluno com média ≥ 60 nunca ser reprovado por faltas. Divergências com a regra
"esperada" são registradas, não corrigidas.

## Autorização (matriz)

| Ação | Aluno | Professor | Secretário |
|---|---|---|---|
| Cadastros (RF-02, RF-03) e matrícula (RF-04), prazos (RF-05) | — | — | sim |
| Lançar notas e faltas (RF-06, RF-07) | — | só nas próprias disciplinas, dentro do prazo | — |
| Ver o próprio boletim (RF-09) | sim | — | — |
| Ver boletim de turma (RF-10) | — | só turmas em que leciona | sim |

Acesso negado responde 403 e não produz efeito colateral.

## Tarefas de usabilidade (objetivos, sem prescrever tela)

- Professor lança as notas de um bimestre para uma turma de 30 alunos.
- Aluno consulta a própria nota numa disciplina.
- Secretário matricula um aluno numa turma.

## Fora do escopo

Horário, aulas, materiais, calendário, chat, unidade escolar, dependência, relatórios em PDF e upload
de arquivos.
