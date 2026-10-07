# Usabilidade — protocolo do avaliador

Mede o esforço de interação (KLM/GOMS) das três tarefas da fatia vertical em cada célula. A
interface de cada célula é diferente por desenho; por isso cada tarefa é **gravada uma vez por
célula** e o harness a reexecuta e pontua.

Os agentes nunca veem este arquivo. As tarefas aqui dão o **objetivo**, não a tela.

## Cenário (criado automaticamente)

| Item | Valor |
|---|---|
| Senha de todos os usuários | `Usabilidade#2026` |
| Secretaria | e-mail `secretaria@escola.test`, matrícula `S0001` |
| Professora | Ana Lima — e-mail `ana.lima@escola.test`, matrícula `P0001` |
| Turma A | 2026 · Ensino Médio · 1º ano — disciplina **Matemática** (Ana Lima), alunos `Aluno 01` … `Aluno 30` |
| Turma B | 2026 · Ensino Médio · 2º ano — disciplina **História** (Ana Lima), aluna **Bruna Consulta** (`bruna@escola.test`, `A0031`), nota 73 no 1º bimestre |
| Aluno sem matrícula | **Carlos Novo** (`carlos@escola.test`, `A0040`) |

## Tarefas

Cada gravação começa na página inicial, **sem sessão**, e inclui a entrada no sistema.

1. **Lançar notas da turma.** Como Ana Lima, lance a nota do 1º bimestre de Matemática dos 30
   alunos da turma A:

   | Aluno | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 |
   |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
   | Nota | 55 | 62 | 71 | 48 | 90 | 66 | 73 | 59 | 81 | 64 | 77 | 52 | 69 | 88 | 60 |

   | Aluno | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30 |
   |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
   | Nota | 45 | 93 | 70 | 58 | 67 | 74 | 61 | 85 | 50 | 79 | 63 | 68 | 57 | 91 | 72 |

2. **Consultar a própria nota.** Como Bruna Consulta, encontre sua nota do 1º bimestre de
   História. A gravação termina com a nota **visível na tela**.
3. **Matricular aluno.** Como a secretaria, matricule Carlos Novo na turma A.

## Como gravar

```bash
# 1. aplicação da célula, com o cenário, em http://127.0.0.1:8080
atena-bench sandbox subir --tech <laravel|go> --repo runs/<run-id>/repo

# 2. noutro terminal, uma gravação por tarefa (mesma versão do Playwright do harness)
mkdir -p runs/<run-id>/artifacts/usabilidade && cd runs/<run-id>/artifacts/usabilidade
npx playwright@1.63.0 codegen --target python -o tarefa-1.py http://127.0.0.1:8080
```

Regras da gravação:

- Faça o caminho que um usuário novo faria: sem digitar URL, sem atalhos que a interface não
  mostra, sem pressa artificial. Use o caminho mais curto que a interface **oferece**.
- Erro de digitação: recomece a gravação; o roteiro gravado é o caminho limpo.
- Não edite o arquivo gerado.
- Feche o navegador ao terminar cada tarefa. Reinicie o `subir` entre as tarefas 1 e 3, que
  alteram dados.

## Pontuação

```bash
atena-bench sandbox usabilidade --tech <tech> --repo runs/<run-id>/repo \
  --roteiros runs/<run-id>/artifacts/usabilidade
```

Numa aplicação nova com o mesmo cenário, o harness reexecuta cada roteiro e confirma pela API se
a tarefa foi concluída. Ele conta as telas (caminhos distintos navegados) e calcula o KLM das ações
gravadas: K 280 ms, P 1100 ms, B 100 ms, H 400 ms, M 1350 ms (Card, Moran & Newell, 1983). Tarefa
não concluída não é pontuada. O resultado vai para `usabilidade.json` e para as métricas
`usab_tarefa_N_*`.

## Ameaças à validade

- Um avaliador só, e o mesmo para todas as células; a ordem das células é aleatorizada.
- KLM estima especialista sem erro: mede o custo mínimo do caminho, não o aprendizado.
- O login entra em todas as tarefas: é custo igual entre células, mas dilui a diferença.
