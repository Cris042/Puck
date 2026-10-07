<?php

use Illuminate\Support\Facades\DB;

class Ruim
{
    public function sql($busca, $pdo)
    {
        DB::select("select * from alunos where nome like '%" . $busca . "%'");
        DB::statement("delete from notas where id = $busca");
        $pdo->query("select * from x where y = " . $busca);
    }

    public function senha($senha)
    {
        $a = md5($senha);
        $b = password_hash($senha, PASSWORD_BCRYPT);
        $pepper = 'c2VncmVkby1maXhvLW5vLWNvZGlnbw==';
        return unserialize($a . $b . $pepper);
    }
}
