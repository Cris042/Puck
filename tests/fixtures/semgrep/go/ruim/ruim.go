package ruim

import (
	"context"
	"crypto/md5"
	"fmt"
	"math/rand"
	"net/http"

	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/bcrypt"
)

const pepper = "c2VncmVkby1maXhvLW5vLWNvZGlnbw=="

func Buscar(ctx context.Context, db *pgxpool.Pool, nome string) {
	db.Query(ctx, fmt.Sprintf("select * from alunos where nome = '%s'", nome))
	db.Exec(ctx, "delete from notas where id = "+nome)
}

func Senha(s string) {
	md5.Sum([]byte(s))
	bcrypt.GenerateFromPassword([]byte(s), 12)
	_ = rand.Int63()
}

func Subir() { http.ListenAndServe(":8080", nil) }
