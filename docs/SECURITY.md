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
Checks como PHPUnit executam código escrito pela LLM. Em `config/checks.atena.yaml` e
`config/hidden-checks.atena.yaml` todos rodam em container com `--network none` e o workspace
montado somente-leitura; nada do código gerado roda no host. Mantenha esse padrão ao adicionar
checks.

## Isolamento do oráculo
Checks ocultos e suas regras ficam fora do workspace (`{config_dir}`) e não são expostos às
ferramentas dos agentes nem ao prompt do revisor. O workspace é clonado sem remote para que o
histórico futuro do projeto-alvo não fique acessível.

## Observação
Checks configurados podem executar comandos locais. Revise `checks.yaml` antes de executar configurações recebidas de terceiros.
