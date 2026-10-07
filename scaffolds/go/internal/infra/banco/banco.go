// Package banco abre a conexão com o PostgreSQL a partir do ambiente (DB_HOST, DB_PORT,
// DB_DATABASE, DB_USERNAME, DB_PASSWORD), o mesmo contrato do esqueleto PHP.
package banco

import (
	"context"
	"fmt"
	"net/url"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"
)

// URL monta a URL de conexão; `esquema` é "postgres" para o pgx e "pgx5" para o migrate.
func URL(esquema string) string {
	endereco := url.URL{
		Scheme:   esquema,
		User:     url.UserPassword(variavel("DB_USERNAME", "escola"), variavel("DB_PASSWORD", "escola")),
		Host:     variavel("DB_HOST", "127.0.0.1") + ":" + variavel("DB_PORT", "5432"),
		Path:     variavel("DB_DATABASE", "escola"),
		RawQuery: "sslmode=disable",
	}
	return endereco.String()
}

// Conectar abre o pool e confirma que o banco responde.
func Conectar(ctx context.Context) (*pgxpool.Pool, error) {
	pool, err := pgxpool.New(ctx, URL("postgres"))
	if err != nil {
		return nil, fmt.Errorf("abrir pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping: %w", err)
	}
	return pool, nil
}

func variavel(nome, padrao string) string {
	if valor := os.Getenv(nome); valor != "" {
		return valor
	}
	return padrao
}
