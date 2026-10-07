# Base técnica comum dos projetos-alvo

Contrato técnico **idêntico para as 8 células** (2 techs × 2 metodologias × 2 repetições). Define o
que todo projeto reescrito precisa ser — arquitetura, estrutura, padrões, segurança, testes e
ferramentas — para que as diferenças medidas venham da metodologia, não de escolhas de base.

Derivado do MinervaFinancas (ADR-003, playbooks de backend e de segurança), expresso de forma
agnóstica e com anexos por stack.

## 0. Papel no experimento

- **Constante, não variável.** Entregue igual a M1 e M2 como requisito não funcional. Diz **o que**
  o projeto precisa cumprir; **como** trabalhar (papéis, gates, ADR/PRD/HLD/FDD, revisão) continua
  sendo exclusivo da M2.
- **Verificável.** Cada regra marcada com ✅ tem verificação automática (seção 9). Regra sem
  verificação é orientação e não entra no índice de qualidade.
- **Congelada** antes da campanha; cópia vai para o `input-snapshot/` de cada execução.
- **Ameaça declarada:** dar a mesma base às duas metodologias reduz a distância entre elas. É o
  preço de medir conformidade de forma comparável.

## 1. Arquitetura

**Monólito modular**, um processo HTTP e um PostgreSQL. Sem microsserviços, filas, cache distribuído,
event sourcing ou CQRS — nenhum requisito da fatia os justifica.

### 1.1 Organização: módulo por entidade, subpasta por função

```
<modulo>/{http, dto, actor, service, builder, dominio, dao, helper}
comum/          ← só o que é compartilhado por mais de um módulo
infra/          ← adaptadores transversais: banco, hash de senha, relógio, sessão
```

Módulos da fatia vertical: `autenticacao`, `pessoa` (aluno, professor, secretário), `turma`,
`matricula`, `disciplina`, `boletim` (notas, recuperação, média, situação), `frequencia`.

### 1.2 Fluxo obrigatório

```
http → actor → { service, builder, helper, dao (via interface) }
```

| Função | Responsabilidade | Não pode |
|---|---|---|
| `http` | recebe e devolve **DTO**; valida forma; mapeia status | conter regra, conhecer DAO, expor entidade |
| `dto` | transporte de entrada e saída, com allowlist de campos | conter comportamento |
| `actor` | orquestra **um** caso de uso; define a transação | calcular regra, montar SQL |
| `service` | regra de negócio pura (média, situação, autorização) | fazer I/O, conhecer HTTP ou DTO |
| `dominio` | entidades, objetos de valor, invariantes | depender de framework, driver ou serialização |
| `builder` | monta domínio e DTO de resposta | decidir regra, acessar banco |
| `dao` | **único** que fala SQL, sempre parametrizado; erros tipados | conter regra, devolver erro cru do driver |
| `helper` | apoio puro, sem estado | guardar estado, fazer I/O |

### 1.3 Contrato de camadas (agnóstico) ✅

| Camada do contrato | Funções que a compõem | Pode depender de |
|---|---|---|
| `domain` | `dominio`, `service` | nada além da linguagem padrão |
| `application` | `actor`, `builder`, `helper`, interfaces de DAO e de adaptadores (portas) | `domain` |
| `infrastructure` | implementações de `dao`, `infra/*` | `application`, `domain` |
| `interface/http` | `http`, `dto` | `application`, `domain` |

Proibido também: dependência entre módulos fora de `actor` → `actor`/`service` público do outro módulo;
ciclos entre módulos. Verificação: Deptrac (PHP) e go-arch-lint (Go).

## 2. Padrões de projeto

| Padrão | Regra | Por quê |
|---|---|---|
| DTO | todo request e response passa por DTO; nunca serializar entidade | evita mass assignment e vazamento de campo interno (ex.: hash de senha) |
| Actor por caso de uso | um caso de uso = um actor, nome no imperativo (`LancarNotasActor`) | fluxo legível e testável |
| DAO com interface | interface na camada de aplicação, implementação na infraestrutura | regra testável sem banco |
| Objeto de valor | `Nota` (0–100), `Matricula`, `Email`, `Bimestre` (1–4), `Situacao` | invariante na construção, não espalhada |
| Erro tipado | `NaoEncontrado`, `Conflito`, `NaoAutorizado`, `Invalido` mapeados para HTTP na borda | erro de banco não vaza |
| Fábrica | só com **duas ou mais** implementações concretas | sem isso é indireção sem ganho |
| Injeção por construtor | dependências explícitas; sem service locator, sem estado global | teste sem container |
| Proibidos | repositório genérico, herança de entidade de framework no domínio, singleton mutável, `Util`/`Manager` sem papel | acoplamento sem responsabilidade |

### 2.1 Nomenclatura

- O nome diz o que a unidade faz; sem abreviação (exceções idiomáticas de Go: `ctx`, `err`, `id`,
  `tx`, `db` em escopo curto).
- Interface: `I` prefixado em PHP (`IBoletimDAO`); em Go, interface nomeada pelo papel
  (`BoletimDAO`) e implementação concreta com sufixo de tecnologia (`BoletimDAOPostgres`).
- Sufixos obrigatórios: `DTO`, `Actor`, `Service`, `Builder`, `DAO`; enum com `Enum` em PHP.
- Domínio e mensagens em **português**; termos técnicos da linguagem no idioma dela.

### 2.2 Object Calisthenics — regras declaradas por linguagem ✅ (parcial)

| # | Regra | PHP | Go |
|---|---|---|---|
| 1 | um nível de indentação por método | sim | sim (função) |
| 2 | sem `else` (retorno antecipado) | sim | sim (idiomático) |
| 3 | encapsular primitivos com significado | sim | sim (tipos nomeados) |
| 4 | coleções de primeira classe quando protegem regra | sim | sim |
| 5 | um ponto por linha | sim, exceto fluent builder do framework | **não se aplica** (encadeamento de método é raro e o idioma é outro) |
| 6 | sem abreviação | sim | sim, com as exceções idiomáticas acima |
| 7 | entidades pequenas: classe ≤ 150 linhas, método ≤ 20 | sim | arquivo ≤ 300 linhas, função ≤ 30 |
| 8 | no máximo duas variáveis de instância | sim, **DTO isento** | **não se aplica** (struct de valor é o idioma) |
| 9 | sem getters/setters | sim, **DTO isento** | sem prefixo `Get`; campos exportados só em DTO |

Verificado: 1, 2 e 7 por métrica (PHPMD/PHPMetrics; gocyclo/funlen via golangci-lint); as demais
pelo juiz.

## 3. Segurança

### 3.1 Senha: Argon2id + pepper ✅

Mesmo algoritmo e mesmos parâmetros nas duas stacks:

```
hash = argon2id( HMAC-SHA256(pepper, senha_utf8), salt aleatório )
armazenado: formato PHC "$argon2id$v=19$m=65536,t=3,p=1$<salt>$<hash>" + pepper_versao
```

| Parâmetro | Valor |
|---|---|
| memória | 64 MiB (`m=65536`) — acima do piso OWASP |
| iterações | `t=3` |
| paralelismo | `p=1` |
| salt | 16 bytes de CSPRNG |
| hash | 32 bytes |
| pepper | ≥ 32 bytes, base64, **só em variável de ambiente** (`APP_PASSWORD_PEPPER`), nunca no banco nem no repositório |
| rotação | coluna `pepper_versao`; pepper antigo aceito para verificar e rehash no login |
| comparação | só pela função da biblioteca (tempo constante) |

- Rehash transparente no login quando os parâmetros ou o pepper mudarem.
- **Senhas legadas (md5):** não são convertíveis. A migração marca `algoritmo = 'md5_legado'`; no
  primeiro login válido, verifica md5 e regrava em Argon2id. Nenhum md5 novo é gravado.
- Política: mínimo 8 caracteres, sem regras de composição.

### 3.2 Autenticação, sessão e autorização ✅

- Sessão **server-side** com token opaco de 32 bytes (CSPRNG); no banco, só o SHA-256 do token.
- Cookie `HttpOnly`, `Secure` (fora de dev), `SameSite=Lax`, `Path=/`; ID rotacionado no login e
  invalidado no logout; expiração absoluta de 8 h e ociosa de 30 min.
- CSRF: token por sessão em toda mutação vinda de formulário; nenhuma mutação via `GET`.
- Login: mensagem única "credenciais inválidas"; hash fictício quando o usuário não existe (tempo
  igual); limite de 5 tentativas/min por conta + IP (`429`).
- Autorização **negada por padrão**; matriz perfil × ação declarada em **um** lugar
  (`autenticacao/service/MatrizAutorizacao`), testada por tabela.

### 3.3 Borda HTTP ✅

SQL só parametrizado; saída HTML sempre escapada pelo template; limite de corpo de 1 MiB; timeouts
de leitura/escrita/ociosidade no servidor; cabeçalhos `Content-Security-Policy`,
`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`; erro 500 sem detalhe interno; logs
sem senha, token, CPF ou pepper.

## 4. Banco de dados

- PostgreSQL (versão fixada no esqueleto). Modelo vindo da tarefa
  [`refatoracao-banco`](../../prompts/tarefas/refatoracao-banco.md).
- Migrações versionadas e reversíveis pela ferramenta da stack; nunca alterar migração já aplicada.
- Chaves estrangeiras, `UNIQUE` de negócio e `CHECK` de domínio (nota 0–100, bimestre 1–4) no banco.
- Chave substituta (`bigint` identidade) + chave natural única; nada de vínculo por nome.
- Valores derivados (média, situação) **calculados pelo `service`**; se persistidos, gravados na
  mesma transação das notas que os originam.
- Transação aberta e fechada pelo `actor`, via interface de unidade de trabalho.
- Dados de seed e de teste **100% sintéticos**.

## 5. Contrato HTTP

- Contrato **JSON fixo** (OpenAPI congelada na etapa 2) para os casos de uso da fatia. É o que o
  oráculo exercita, idêntico para as duas stacks.
- Interface web **renderizada no servidor** (Blade / `html/template`), sem SPA e com JavaScript
  mínimo. O desenho das telas é livre, porque a usabilidade mede design (protocolo, seção 4.4).
- Status: `200` leitura/atualização, `201` criação, `204` sem corpo, `400` forma inválida, `401` sem
  sessão, `403` sem permissão, `404`, `409` conflito, `422` regra violada, `429` limite, `500` sem
  detalhe.
- Corpo de erro: `{"erro": {"codigo": "...", "mensagem": "..."}}`. Listagens paginadas com limite
  máximo.
- `GET /saude` sem autenticação, para o harness saber que a aplicação subiu.

## 6. Testes

| Nível | O que cobre | Banco | Obrigatório |
|---|---|---|---|
| Unitário | `dominio`, `service`, `builder`, `helper` | não | sim |
| Integração | `dao` contra PostgreSQL real (container) | sim | sim |
| HTTP | `http` + `actor` ponta a ponta, autorização por perfil | sim | sim |

- **Cobertura de linhas ✅:** ≥ 80% no projeto e ≥ 90% em `dominio` + `service`. Abaixo disso o
  check falha.
- Regra de média e situação coberta por **teste de tabela** com os casos-limite (nota vazia,
  recuperação maior e menor que a nota, média exatamente 60, menos de 4 bimestres, faltas acima do
  limite com média ≥ 60).
- Matriz de autorização coberta por tabela perfil × ação.
- Testes idempotentes, independentes de ordem, padrão Arrange-Act-Assert, nomes que descrevem o
  comportamento.
- O oráculo oculto é **separado** destes testes: o projeto não o vê.

## 7. Configuração, execução e entrega

- Configuração só por variável de ambiente; `.env.example` sem segredo; `.env` no `.gitignore`.
- `Dockerfile` multi-stage e `compose.yaml` com `app` + `postgres` e healthcheck.
- **Alvos de `make` com o mesmo nome nas duas stacks** (são o que `checks.yaml` chama):

| Alvo | Faz |
|---|---|
| `make up` / `make down` | sobe e derruba app + banco |
| `make migrate` | aplica migrações |
| `make seed` | carrega dados sintéticos |
| `make test` | todos os testes |
| `make coverage` | testes com relatório de cobertura (Cobertura XML em `build/coverage.xml`) |
| `make lint` | formatação + análise estática |
| `make arch` | conformidade de camadas |
| `make audit` | vulnerabilidades de dependências |

- Logs estruturados em JSON no stdout.
- Dependência nova só com versão fixada e finalidade declarada no README do projeto.

## 8. Ferramentas

Versões exatas congeladas no esqueleto de cada stack (fase B) e registradas no `input-snapshot/`.

| Finalidade | PHP / Laravel | Go | Comparável entre techs |
|---|---|---|---|
| Runtime / framework | PHP 8.4+ / Laravel (estável na data do congelamento) | Go (estável na data) + `net/http` da biblioteca padrão | — |
| Banco / driver | PostgreSQL / PDO via Query Builder **só em `dao`** | PostgreSQL / `pgx` | — |
| Migrações | migrations do Laravel | `golang-migrate` (SQL) | — |
| Senha | `password_hash(PASSWORD_ARGON2ID)` + `hash_hmac` | `golang.org/x/crypto/argon2` + `crypto/hmac` | sim (mesmos parâmetros) |
| Testes | PHPUnit + pcov | `go test` + `-coverprofile` | sim |
| Formatação | Laravel Pint | `gofmt` | — |
| Análise estática | PHPStan nível máximo + Larastan | `go vet` + `staticcheck` | sim |
| Camadas | Deptrac | go-arch-lint | sim |
| Complexidade | PHPMetrics / PHPMD | gocyclo | sim |
| Complexidade cruzada | **lizard** | **lizard** | **sim (mesma ferramenta)** |
| Duplicação | **jscpd** | **jscpd** | **sim (mesma ferramenta)** |
| Acoplamento / coesão | PHPMetrics | análise de imports | aproximado / só PHP |
| Dependências vulneráveis | `composer audit` | `govulncheck` | sim |
| SAST | Semgrep (regras fixas por linguagem) | Semgrep | sim |

`phpcpd` foi arquivado; jscpd substitui `phpcpd` e `dupl` com a vantagem de ser a mesma medida nas
duas linguagens.

## 9. O que é verificado automaticamente

| Regra | Check |
|---|---|
| Contrato de camadas (1.3) | `make arch` |
| Argon2id + parâmetros + pepper fora do código (3.1) | teste do oráculo lendo o hash gravado + Semgrep |
| Sessão, cookie, CSRF, rate limit (3.2) | oráculo HTTP + ZAP |
| SQL parametrizado, escape, headers (3.3) | Semgrep + ZAP |
| Cobertura (6) | `make coverage` |
| Complexidade e tamanho (2.2: 1, 2, 7) | lizard + ferramenta da stack |
| Contrato HTTP (5) | oráculo HTTP |

## Anexo A — Estrutura de referência PHP/Laravel

```
app/
  Modulos/
    Boletim/{Http,Dto,Actor,Service,Builder,Dominio,Dao,Helper}/
    Autenticacao/…  Pessoa/…  Turma/…  Matricula/…  Disciplina/…  Frequencia/…
  Comum/
  Infra/{Banco,Senha,Sessao,Relogio}/
database/migrations/   database/seeders/
routes/web.php   routes/api.php
resources/views/
tests/{Unit,Integracao,Http}/
deptrac.yaml   phpstan.neon   Makefile   compose.yaml   Dockerfile
```

Eloquent, se usado, fica restrito a `Dao/` e nunca sai dele; o domínio não estende classes do
framework.

## Anexo B — Estrutura de referência Go

```
cmd/servidor/main.go
internal/
  boletim/{http,dto,actor,service,builder,dominio,dao,helper}/
  autenticacao/…  pessoa/…  turma/…  matricula/…  disciplina/…  frequencia/…
  comum/
  infra/{banco,senha,sessao,relogio}/
migrations/   web/templates/
.go-arch-lint.yml   Makefile   compose.yaml   Dockerfile
```

Testes ao lado do código (`*_test.go`); integração com build tag `integracao`.
