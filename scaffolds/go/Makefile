# Alvos da base técnica (seção 7). Os mesmos nomes existem no projeto PHP: o harness chama estes
# alvos dentro da imagem de checks dele, com o ambiente (DB_*, pepper) já definido.
# Ferramentas (staticcheck, go-arch-lint, govulncheck, gocover-cobertura) vêm instaladas na
# imagem do harness; localmente, instale-as nas versões de docker/checks/go/Dockerfile do Puck.
GO ?= go
PORT ?= 8080

.PHONY: up down migrate seed run test coverage lint arch audit

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	$(GO) run ./cmd/migrar

seed:
	@echo "sem seed no esqueleto"

run:
	$(GO) build -o build/servidor ./cmd/servidor
	PORT=$(PORT) ./build/servidor

# `integracao` habilita os testes que usam o PostgreSQL do ambiente.
test:
	$(GO) test -tags integracao ./...

coverage:
	mkdir -p build
	$(GO) test -tags integracao -coverpkg=./... -coverprofile=build/cover.out ./...
	gocover-cobertura < build/cover.out > build/coverage.xml
	$(GO) tool cover -func=build/cover.out | tail -1

lint:
	@test -z "$$(gofmt -l .)" || (echo "arquivos sem gofmt:"; gofmt -l .; exit 1)
	$(GO) vet ./...
	staticcheck ./...

arch:
	go-arch-lint check

audit:
	govulncheck ./...
