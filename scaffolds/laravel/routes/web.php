<?php

use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    return view('welcome');
});

// Contrato com o harness (base técnica, seção 5): responde 200 quando a aplicação está no ar.
Route::get('/saude', fn () => response()->json(['status' => 'ok']));
