# "Tech" interna do sandbox: roda a implementação de referência para validar oráculo, k6 e ZAP.
FROM python:3.13.16-slim
RUN apt-get update && apt-get install -y --no-install-recommends make \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /work
