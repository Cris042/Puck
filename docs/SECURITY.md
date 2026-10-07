# Segurança do harness

O implementador não recebe um shell arbitrário. Ele pode manipular somente arquivos dentro da cópia isolada do repositório e executar checks previamente allowlisted no YAML de configuração.

## Proteções
- bloqueio de path traversal;
- bloqueio de acesso direto a `.git` pelas ferramentas de arquivo;
- workspace isolado por execução;
- comandos de validação definidos pelo operador, não pela LLM;
- chaves de API somente via variáveis de ambiente;
- `.env` ignorado pelo Git.

## Execução do código gerado
Checks executam código escrito pela LLM. Em `config/checks.<tech>.yaml` eles rodam em container
com o workspace montado somente-leitura e imagem **do harness** (`puck-checks-<tech>`): o
`compose.yaml` do projeto é escrito pela LLM e nunca define o próprio sandbox. Nada do código
gerado roda no host. Mantenha esse padrão ao adicionar checks.

## Sandbox (`src/atena_benchmark/sandbox.py`)
- Dependências do projeto: baixadas **com** rede, mas sem executar código do projeto
  (`composer install --no-scripts --no-plugins`, `go mod download`).
- Execução (testes, aplicação, oráculo, carga, DAST): sem internet. Quando há banco, numa rede
  Docker `--internal` com PostgreSQL efêmero em tmpfs; sem banco, `--network none`.
- Segredos da aplicação (`APP_KEY`, pepper, primeiro secretário) gerados a cada execução.
- A única exceção de rede de saída é a auditoria de dependências, que consulta a base de
  vulnerabilidades sem executar o projeto.
- `sandbox subir` (gravação de usabilidade) publica só em `127.0.0.1`, por uma ponte `socat`; a
  aplicação continua sem rota para a internet.

## Legado
O legado é exportado no SHA fixado **sem `.git`** (nem histórico nem commits posteriores, que
incluem uma reescrita pública) e com arquivos somente-leitura. As ferramentas `legado_*` só leem,
com `pathguard`.

## Dados
Somente dados sintéticos em prompts, seeds, testes e índice. O dump MariaDB de 2020 é versionado
só como estrutura (`spec/legado/`), sem os INSERTs com dados pessoais.

## Isolamento do oráculo
Checks ocultos e suas regras ficam fora do workspace (`{config_dir}`) e não são expostos às
ferramentas dos agentes nem ao prompt do revisor. O workspace é clonado sem remote para que o
histórico futuro do projeto-alvo não fique acessível.

## Observação
Checks configurados podem executar comandos locais. Revise `checks.yaml` antes de executar configurações recebidas de terceiros.

## CAI (exploração ofensiva)
Complementar e qualitativo, **fora do score** (não determinístico). Só contra a aplicação local
publicada por `atena-bench sandbox subir`, com `CAI_TELEMETRY=False`. Os achados entram no artigo
como observação, nunca como métrica comparada.
