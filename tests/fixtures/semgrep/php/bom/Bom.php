<?php

use Illuminate\Support\Facades\DB;

class Bom
{
    public function sql($busca)
    {
        return DB::select('select * from alunos where nome like ?', ['%' . $busca . '%']);
    }

    public function senha($senha)
    {
        $pepper = getenv('APP_PASSWORD_PEPPER');
        return password_hash(hash_hmac('sha256', $senha, $pepper), PASSWORD_ARGON2ID);
    }
}
