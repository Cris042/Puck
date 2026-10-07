<?php

namespace App\Modulos\Boletim\Dao;

interface IBoletimDAO
{
    public function notas(int $alunoId): array;
}
