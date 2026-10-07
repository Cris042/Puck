package banco

import "testing"

func TestURLUsaAmbiente(t *testing.T) {
	t.Setenv("DB_HOST", "pg")
	t.Setenv("DB_PORT", "6543")
	t.Setenv("DB_DATABASE", "teste")
	t.Setenv("DB_USERNAME", "u")
	t.Setenv("DB_PASSWORD", "s")

	if got, want := URL("postgres"), "postgres://u:s@pg:6543/teste?sslmode=disable"; got != want {
		t.Fatalf("URL = %q, esperado %q", got, want)
	}
}
