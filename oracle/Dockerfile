# Oráculo HTTP do harness. Nunca exposto aos agentes: roda depois da execução, na rede interna da
# aplicação, com a suíte e o dataset dourado montados somente leitura.
FROM python:3.13.16-slim
RUN pip install --no-cache-dir pytest==9.1.1 httpx==0.28.1
WORKDIR /oracle
ENTRYPOINT ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "/oracle/suite"]
