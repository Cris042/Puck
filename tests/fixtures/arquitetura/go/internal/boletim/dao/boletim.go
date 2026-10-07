// Package dao persiste o boletim.
package dao

import "github.com/jackc/pgx/v5/pgxpool"

// BoletimDAOPostgres grava notas no PostgreSQL.
type BoletimDAOPostgres struct{ Pool *pgxpool.Pool }

// Salvar grava uma nota.
func (d BoletimDAOPostgres) Salvar(int) error { return nil }
