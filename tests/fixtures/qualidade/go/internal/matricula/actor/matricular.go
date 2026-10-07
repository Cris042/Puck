// Package actor orquestra a matrícula.
package actor

import boletim "escola/internal/boletim/actor"

// MatricularActor depende do boletim (ciclo deliberado entre módulos).
type MatricularActor struct{ Boletim boletim.ConsultarBoletimActor }

// Executar consulta o boletim do aluno matriculado.
func (a MatricularActor) Executar(alunoID int) []float64 { return a.Boletim.Executar(alunoID) }
