# Analyzers de qualidade independentes de linguagem (mesma medida em PHP e Go):
# lizard (complexidade ciclomática, tamanho de função) e jscpd (duplicação).
FROM python:3.13.16-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
 && npm install -g jscpd@5.4.0 \
 && pip install --no-cache-dir lizard==1.24.1 \
 && apt-get clean && rm -rf /var/lib/apt/lists/* /root/.npm
WORKDIR /src
