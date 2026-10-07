<?php

namespace App\Modulos\Boletim\Dao;

use Illuminate\Support\Facades\DB;

final class BoletimDAOPostgres
{
    public function salvar(int $nota): void
    {
        DB::insert('insert into notas (valor) values (?)', [$nota]);
    }
}
