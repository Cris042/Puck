<?php

namespace App\Modulos\Boletim\Dominio;

use App\Modulos\Boletim\Dao\BoletimDAOPostgres;
use Illuminate\Support\Facades\Log;

final class Nota
{
    public function __construct(private int $valor)
    {
        Log::info('violação 1: domínio depende do framework');
    }

    public function persistir(BoletimDAOPostgres $dao): void
    {
        $dao->salvar($this->valor); // violação 2: domínio depende da infraestrutura
    }
}
