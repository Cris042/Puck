// Package actor orquestra a consulta do boletim.
package actor

import "escola/internal/matricula/service"

// BoletimDAO é a porta de leitura do boletim.
type BoletimDAO interface {
	Notas(alunoID int) []float64
}

// ConsultarBoletimActor consulta o boletim de um aluno matriculado.
type ConsultarBoletimActor struct{ DAO BoletimDAO }

// Executar devolve as notas, ou nada se o aluno não estiver matriculado.
func (a ConsultarBoletimActor) Executar(alunoID int) []float64 {
	if !service.Ativa(alunoID) {
		return nil
	}
	return a.DAO.Notas(alunoID)
}
