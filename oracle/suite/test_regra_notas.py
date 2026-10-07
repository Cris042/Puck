"""RF-06 a RF-10: a regra de notas comparada com o dataset dourado do legado.

O dourado foi obtido EXECUTANDO o Atena legado (oracle/dataset/notas-dourado.json). Um teste por
caso: a métrica conta quantos comportamentos do legado a reescrita preserva.
"""

from __future__ import annotations

import json
from collections import defaultdict

import pytest
from conftest import DOURADO

TOLERANCIA = 0.005  # o contrato permite arredondar média e média parcial a 2 casas

DATASET = json.loads(DOURADO.read_text(encoding="utf-8"))
CASOS = DATASET["casos"]
AMOSTRA_ALUNO = {c["id"] for c in CASOS[:6]}


def _numero(valor: str | None):
    if valor in (None, ""):
        return None
    numero = float(valor)
    return int(numero) if numero.is_integer() else numero


@pytest.fixture(scope="module")
def boletins(fabrica, secretario):
    """Monta uma turma por carga horária, lança tudo pelo contrato e lê os boletins."""
    por_ch = defaultdict(list)
    for caso in CASOS:
        por_ch[caso["carga_horaria"]].append(caso)

    linhas, visoes_aluno = {}, {}
    for ch, casos in sorted(por_ch.items()):
        turma = fabrica.turma()
        professor = fabrica.pessoa("professores")
        disciplina = fabrica.disciplina(turma, professor, carga_horaria=ch)
        alunos = {}
        for caso in casos:
            alunos[caso["id"]] = fabrica.pessoa("alunos")
            fabrica.matricular(turma, alunos[caso["id"]])
        api = fabrica.sessao(professor)

        maior = max((len(c["faltas"]) for c in casos), default=0)
        for i in range(maior):
            registros = [{"aluno_id": alunos[c["id"]].id, "faltas": c["faltas"][i]}
                         for c in casos if len(c["faltas"]) > i]
            corpo = {"data": f"2026-03-{i + 1:02d}", "bimestre": 1, "registros": registros}
            resposta = api.post(f"/api/disciplinas/{disciplina}/faltas", corpo)
            assert resposta.status_code == 201, resposta.text[:300]

        lancamentos = [
            {"aluno_id": alunos[c["id"]].id,
             "notas": [_numero(v) for v in c["notas"]],
             "recuperacoes": [_numero(v) for v in c["recuperacoes"]]}
            for c in casos
        ]
        resposta = api.put(f"/api/disciplinas/{disciplina}/notas", {"lancamentos": lancamentos})
        assert resposta.status_code == 200, resposta.text[:300]

        boletim = secretario.get(f"/api/disciplinas/{disciplina}/boletim")
        assert boletim.status_code == 200, boletim.text[:300]
        por_aluno = {linha["aluno_id"]: linha for linha in boletim.json()["alunos"]}
        for caso in casos:
            linhas[caso["id"]] = por_aluno.get(alunos[caso["id"]].id)
            if caso["id"] in AMOSTRA_ALUNO:
                proprio = fabrica.sessao(alunos[caso["id"]]).get("/api/alunos/eu/boletim")
                visoes_aluno[caso["id"]] = (proprio.status_code, proprio.json(), disciplina)
    return linhas, visoes_aluno


def _confere(linha: dict, esperado: dict, caso: dict) -> None:
    assert linha is not None, "aluno matriculado ausente do boletim"
    assert linha["situacao"] == esperado["situacao"], "situação"
    assert linha["media"] == pytest.approx(esperado["media"], abs=TOLERANCIA), "média"
    assert linha["media_parcial"] == pytest.approx(esperado["media_parcial"], abs=TOLERANCIA), "média parcial"
    assert linha["faltas"] == sum(caso["faltas"]), "faltas somadas"
    gravadas = [_numero(v) for v in esperado["notas_gravadas"]]
    assert [None if v is None else pytest.approx(v) for v in gravadas] == linha["notas"], "notas limitadas a 100"


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_caso_dourado(boletins, caso):
    linhas, _ = boletins
    _confere(linhas[caso["id"]], caso["esperado"], caso)


@pytest.mark.parametrize("caso_id", sorted(AMOSTRA_ALUNO))
def test_aluno_ve_o_mesmo_resultado(boletins, caso_id):
    _, visoes = boletins
    status, corpo, disciplina = visoes[caso_id]
    assert status == 200
    linha = next(d for d in corpo["disciplinas"] if d["disciplina_id"] == disciplina)
    caso = next(c for c in CASOS if c["id"] == caso_id)
    _confere(linha, caso["esperado"], caso)
