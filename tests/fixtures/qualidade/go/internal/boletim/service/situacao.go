// Package service calcula a situação do aluno.
package service

// Situacao aplica a regra de aprovação do legado.
func Situacao(media float64, lancados, faltas, cargaHoraria int) string {
	if media >= 60 && lancados == 4 {
		return "aprovado"
	}
	if faltas*3300 > cargaHoraria*2700 {
		return "reprovado_por_faltas"
	}
	if media < 60 && lancados == 4 {
		return "reprovado"
	}
	if lancados == 0 {
		return "cursando"
	}
	return "cursando"
}

// SomaA soma as notas lançadas.
func SomaA(notas []*float64) float64 {
	soma, lancados := 0.0, 0
	for _, nota := range notas {
		if nota == nil {
			continue
		}
		soma += min(*nota, 100)
		lancados++
	}
	media := soma / 4
	parcial := soma / float64(max(lancados, 1))
	return media + parcial
}

// SomaB repete SomaA (duplicação deliberada).
func SomaB(notas []*float64) float64 {
	soma, lancados := 0.0, 0
	for _, nota := range notas {
		if nota == nil {
			continue
		}
		soma += min(*nota, 100)
		lancados++
	}
	media := soma / 4
	parcial := soma / float64(max(lancados, 1))
	return media + parcial
}
