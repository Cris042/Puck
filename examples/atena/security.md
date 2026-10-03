# Requisitos de segurança

- Não confiar em entrada do usuário.
- Usar consultas parametrizadas para dados variáveis.
- Evitar nomes de tabela/coluna controlados diretamente por entrada externa.
- Validar uploads por extensão, MIME/tipo real, tamanho e destino permitido.
- Impedir path traversal em leitura e escrita de arquivos.
- Não registrar segredos, senhas ou tokens em texto puro.
- Preservar autorização por perfil em ações sensíveis.
- Tratar sessão e autenticação de forma explícita.
- Não afirmar que a solução é segura apenas por inspeção da LLM; segurança deve ser apoiada por testes e ferramentas.
