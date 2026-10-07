<?php

namespace App\Modulos\Boletim\Service;

final class SituacaoService
{
    public function situacao(float $media, int $lancados, int $faltas, int $cargaHoraria): string
    {
        if ($media >= 60 && $lancados === 4) {
            return 'aprovado';
        }
        if ($faltas * 3300 > $cargaHoraria * 2700) {
            return 'reprovado_por_faltas';
        }
        if ($media < 60 && $lancados === 4) {
            return 'reprovado';
        }
        if ($lancados === 0) {
            return 'cursando';
        }
        return 'cursando';
    }

    public function somaDuplicadaA(array $notas): float
    {
        $soma = 0.0;
        foreach ($notas as $nota) {
            if ($nota === null) {
                continue;
            }
            $soma += min((float) $nota, 100.0);
        }
        $media = $soma / 4;
        $parcial = $soma / max(count(array_filter($notas, fn ($n) => $n !== null)), 1);
        return $media + $parcial;
    }

    public function somaDuplicadaB(array $notas): float
    {
        $soma = 0.0;
        foreach ($notas as $nota) {
            if ($nota === null) {
                continue;
            }
            $soma += min((float) $nota, 100.0);
        }
        $media = $soma / 4;
        $parcial = $soma / max(count(array_filter($notas, fn ($n) => $n !== null)), 1);
        return $media + $parcial;
    }
}
