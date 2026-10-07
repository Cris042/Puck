// Package dominio guarda os valores do boletim.
package dominio

import (
	"escola/internal/boletim/dao"

	"github.com/jackc/pgx/v5"
)

// Nota é uma nota de 0 a 100.
type Nota int

// violação 1: domínio depende da infraestrutura; violação 2: de biblioteca de terceiros.
var (
	_ = dao.BoletimDAOPostgres{}
	_ = pgx.ErrNoRows
)
