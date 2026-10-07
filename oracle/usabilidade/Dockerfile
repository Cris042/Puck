# Reexecução dos roteiros de usabilidade gravados (playwright codegen) contra a aplicação no
# sandbox. Navegadores da imagem oficial; pacote Python na MESMA versão do codegen usado.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
RUN pip install --no-cache-dir --break-system-packages playwright==1.63.0
WORKDIR /usabilidade
