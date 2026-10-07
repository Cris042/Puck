<?php

namespace App\Modulos\Matricula\Service;

final class MatriculaService
{
    public function ativa(int $alunoId): bool
    {
        return $alunoId > 0;
    }
}
