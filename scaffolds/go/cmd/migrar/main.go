// Aplica as migrações SQL de migrations/ no banco de $DB_* (alvo `make migrate`).
package main

import (
	"errors"
	"io/fs"
	"log/slog"
	"os"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/pgx/v5"
	_ "github.com/golang-migrate/migrate/v4/source/file"

	"escola/internal/infra/banco"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	migrador, err := migrate.New("file://migrations", banco.URL("pgx5"))
	if err != nil {
		logger.Error("migração não iniciou", "erro", err)
		os.Exit(1)
	}
	err = migrador.Up()
	if err != nil && !errors.Is(err, migrate.ErrNoChange) && !errors.Is(err, fs.ErrNotExist) {
		logger.Error("migração falhou", "erro", err)
		os.Exit(1)
	}
	logger.Info("migrações aplicadas")
}
