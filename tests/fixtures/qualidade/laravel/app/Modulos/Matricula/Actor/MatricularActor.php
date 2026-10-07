<?php

namespace App\Modulos\Matricula\Actor;

use App\Modulos\Boletim\Actor\ConsultarBoletimActor;

final class MatricularActor
{
    public function __construct(private ConsultarBoletimActor $boletim) {}

    public function executar(int $alunoId): array
    {
        return $this->boletim->executar($alunoId);
    }
}
