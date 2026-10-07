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
