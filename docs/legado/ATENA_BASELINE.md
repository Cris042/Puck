# Atena — baseline do legado

> **Histórico.** Levantamento feito para a trilha antiga (modernização in-place), removida pela
> decisão D-01 de [`docs/PLANO.md`](../PLANO.md). Os checks citados não existem mais no Puck; os
> problemas confirmados por leitura de código continuam válidos como conhecimento do legado. O
> modelo de dados atualizado está em [`MER_DER.md`](MER_DER.md).

Levantamento do commit `ac48dc552b817233547104a5d0acba932d41ab91` (main em 2026-10-03), usado
como `base_ref` fixo em `examples/atena/experiment*.yaml`. Os números abaixo foram medidos com
os checks deste repositório (`config/checks.atena.yaml` e `config/hidden-checks.atena.yaml`).

## Perfil técnico

| Item | Valor observado |
|---|---|
| Linguagem | PHP procedural com classes estáticas, ~139 arquivos próprios, ~15,4 mil linhas |
| Runtime | **PHP 7.3** — `composer.lock` fixa `mpdf/mpdf` v8.0.0 (`php: ~7.3.0`) |
| Dependências | Versionadas em `Lib/vendor` (mPDF, FPDI, deep-copy, psr/log); `composer.json` tem nome trocado (`mpdf/mpdf`) e não define `vendor-dir` |
| Banco | MySQL via PDO (`Models/MySql.php`); **schema não está no repositório** |
| Roteamento | `index.php` + `Models/Router.php` para páginas; `Models/ajax/*.php` acessados diretamente por HTTP |
| Testes | Nenhum |
| CI | `.github/workflows/php.yml` só valida `composer.json`; não roda testes |
| Configuração | `config.php` com `root`/senha vazia e `INCLUDE_PATH` fixo em `http://localhost/Sistema Escolar/` |

## Checks no baseline

| Check | Visível aos agentes | Resultado no baseline |
|---|---|---|
| `php_lint` (PHP 7.3) | sim | passa |
| `phpunit` | sim | indisponível (não há suíte) |
| `phpstan` nível 0 | sim | 4 erros, incluindo 2 fatais (`Cannot use [] for reading` em `Views/pages/boletim-aluno.php:15` e `Views/pages/historico.php:19`) e variável indefinida `$nomee` em `Models/MainMolde.php:641` |
| `semgrep_security` | **não** (oráculo) | 64 SQL interpolado, 4 hash md5 de senha, 44 tokens de sessão previsíveis, 3 uploads sem validação de tipo, 2 credenciais fixas, 599 saídas sem escape |
| `semgrep_architecture` | **não** (oráculo) | 53 acessos ao banco dentro de Views, 85 superglobais fora da borda HTTP |
| `ajax_sem_sessao` | **não** (oráculo) | 8 de 13 endpoints em `Models/ajax` não referenciam a sessão |

## Problemas confirmados por leitura de código

- **Execução remota de código por upload.** `MainMolde::upload()` valida `$formatoArquivo[1]`
  (a primeira extensão), mas grava com a última: `trabalho.pdf.php` passa e é salvo como `.php`
  em `Views/uploads/`, diretório servido pelo Apache.
- **SQL injection** nas buscas de `listagem-alunos`, `listagem-professores`, `listagem-sectarios`
  e `chat` (`$_POST['busca']` interpolado) e em `Models/ajax/Calendario.php` (`$_POST['data']`).
- **Senhas em md5** sem salt (`HomeMolde::login` e cadastros).
- **Token de sessão** = `md5(matrícula + IP + User-Agent)`: previsível e quebra com troca de IP.
- **Endpoints AJAX sem autenticação** — ex.: `CadastroNotas.php`, `EnviarAlaiacao.php`,
  `Calendario.php`.
- **Regra de notas misturada com HTTP e SQL** em `Models/ajax/CadastroNotas.php`; a ordem de
  avaliação aprova média ≥ 60 antes de checar excesso de faltas (preservar ou corrigir é decisão
  de negócio — ver pendências).
- Coluna com nome inconsistente (`atasada_nota04` × `atrasada_nota01..03`) — depende do schema.

## Pendências: documentos e artefatos que faltam

Em ordem de impacto no benchmark.

1. **Schema MySQL + dados de seed anonimizados** (bloqueante para regressão funcional). Sem isso
   não há como subir a aplicação nem escrever a suíte de caracterização; "regressão" hoje é
   medida só por análise estática e pelo juiz.
2. **Suíte de caracterização HTTP (golden master)** mantida fora do repositório do Atena e
   executada como check oculto: login por perfil, lançamento de notas, boletim, upload,
   calendário. Depende do item 1.
3. **Matriz de autorização**: qual perfil (aluno, professor, secretaria) pode acessar cada rota e
   cada endpoint AJAX. Sem ela, a tarefa T-003 deixa o modelo adivinhar a regra.
4. **Decisão sobre defeitos existentes**: preservar ou corrigir (ex.: aprovação ignorando faltas,
   páginas que hoje dão erro fatal). REQ-009 diz "não introduzir regressões", mas não diz se um
   bug existente é comportamento a preservar.
5. **Decisão de runtime alvo**: manter PHP 7.3 (fiel ao `composer.lock`) ou migrar para 8.x como
   parte do experimento. Hoje o contrato fixa 7.3.
6. **Validação do catálogo `examples/atena/tasks.yaml`** pelo dono do sistema: tarefas, critérios
   de aceite e se o escopo é adequado ao orçamento.
7. **Rubrica e pesos da comparação**: como combinar custo, aprovação, regressões e notas do juiz
   em uma leitura final (pré-registrar antes de rodar, para não escolher a métrica depois de ver
   o resultado).
8. **Decisão DDD × simplicidade**: a regra de ferro 7 do Minerva (DDD em toda aplicação
   consumidora) colide com "não criar abstrações especulativas" da arquitetura-alvo. O perfil
   `governance/minerva-benchmark.md` adota DDD proporcional; isso precisa de aval explícito
   (regra 10 do Minerva: conflito entre regras é decisão do usuário).
