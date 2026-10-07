# Escola — esqueleto Go

Ponto de partida fixo das células Go do benchmark. Contém só o servidor HTTP da biblioteca padrão
com `GET /saude`, a conexão com PostgreSQL (`pgx`), o comando de migração (`golang-migrate`) e os
alvos de `make` da base técnica.

```bash
cp .env.example .env   # preencha APP_PASSWORD_PEPPER
make up                # app + PostgreSQL em http://localhost:8080
make test lint arch coverage
```

`GET /saude` responde `{"status": "ok"}` quando a aplicação está no ar.
