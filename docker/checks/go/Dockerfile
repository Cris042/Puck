# Imagem de checks do HARNESS para a stack Go. Nunca construída a partir do workspace.
# Versões fixadas na data do congelamento (2026-10-07); atualizar = mudar o tratamento.
FROM golang:1.27.1

RUN apt-get update && apt-get install -y --no-install-recommends make \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN go install honnef.co/go/tools/cmd/staticcheck@v0.8.1 \
 && go install github.com/fe3dback/go-arch-lint@v1.19.0 \
 && go install golang.org/x/vuln/cmd/govulncheck@v1.8.0 \
 && go install github.com/fzipp/gocyclo/cmd/gocyclo@v0.6.0 \
 && go install github.com/boumenot/gocover-cobertura@v1.5.0 \
 && rm -rf /root/.cache /go/pkg/mod

# Ferramentas instaladas acima; o módulo do projeto usa o cache montado em /deps.
ENV GOTOOLCHAIN=local \
    CGO_ENABLED=0 \
    GOCACHE=/tmp/gocache

WORKDIR /work
