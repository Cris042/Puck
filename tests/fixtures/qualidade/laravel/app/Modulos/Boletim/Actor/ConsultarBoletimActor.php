<?php

namespace App\Modulos\Boletim\Actor;

use App\Modulos\Boletim\Dao\IBoletimDAO;
use App\Modulos\Matricula\Service\MatriculaService;

final class ConsultarBoletimActor
{
    public function __construct(private IBoletimDAO $dao, private MatriculaService $matriculas) {}

    public function executar(int $alunoId): array
    {
        return $this->matriculas->ativa($alunoId) ? $this->dao->notas($alunoId) : [];
    }
}
