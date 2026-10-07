<?php

namespace App\Modulos\Boletim\Dominio;

final class Nota
{
    public function __construct(private float $valor) {}

    public function valor(): float
    {
        return $this->valor;
    }
}
