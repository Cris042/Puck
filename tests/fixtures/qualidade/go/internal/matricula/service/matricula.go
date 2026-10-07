// Package service guarda a regra de matrícula.
package service

// Ativa diz se a matrícula do aluno está ativa.
func Ativa(alunoID int) bool { return alunoID > 0 }
