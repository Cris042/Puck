// Package dominio guarda os valores do boletim.
package dominio

// Nota é uma nota de 0 a 100.
type Nota float64

// Valor devolve a nota como número.
func (n Nota) Valor() float64 { return float64(n) }
