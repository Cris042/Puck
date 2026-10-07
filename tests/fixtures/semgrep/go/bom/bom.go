package bom

import (
	"context"
	"crypto/rand"
	"net/http"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/argon2"
)

func Buscar(ctx context.Context, db *pgxpool.Pool, nome string) {
	db.Query(ctx, "select * from alunos where nome = $1", nome)
}

func Senha(s string) []byte {
	salt := make([]byte, 16)
	_, _ = rand.Read(salt)
	pepper := os.Getenv("APP_PASSWORD_PEPPER")
	return argon2.IDKey([]byte(pepper+s), salt, 3, 64*1024, 1, 32)
}

func Subir() error {
	servidor := &http.Server{Addr: ":8080", ReadHeaderTimeout: 5 * time.Second}
	return servidor.ListenAndServe()
}
