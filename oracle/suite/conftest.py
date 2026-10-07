"""Infraestrutura do oráculo: cliente HTTP por usuário e fábrica de dados sintéticos.

Ambiente: TARGET_URL (aplicação) e PUCK_BOOTSTRAP_{NOME,EMAIL,MATRICULA,SENHA} (primeiro
secretário, o mesmo injetado na aplicação). Todos os dados são sintéticos e únicos por execução.
"""

from __future__ import annotations

import os
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

DOURADO = Path(os.environ.get("PUCK_DOURADO", Path(__file__).parents[1] / "dataset/notas-dourado.json"))


class Api:
    """Um navegador: guarda os cookies de um usuário."""

    def __init__(self, base_url: str):
        self.http = httpx.Client(base_url=base_url, timeout=60, follow_redirects=False)

    def login(self, email: str, matricula: str, senha: str) -> httpx.Response:
        return self.post("/api/sessao", {"email": email, "matricula": matricula, "senha": senha})

    def get(self, path: str) -> httpx.Response:
        return self.http.get(path, headers={"Accept": "application/json"})

    def post(self, path: str, body: dict) -> httpx.Response:
        return self.http.post(path, json=body, headers={"Accept": "application/json"})

    def put(self, path: str, body: dict) -> httpx.Response:
        return self.http.put(path, json=body, headers={"Accept": "application/json"})

    def delete(self, path: str) -> httpx.Response:
        return self.http.delete(path, headers={"Accept": "application/json"})


def unico(prefixo: str) -> str:
    return f"{prefixo}{uuid.uuid4().hex[:10]}"


@dataclass
class Pessoa:
    id: int
    nome: str
    email: str
    matricula: str
    senha: str


def criado(resposta: httpx.Response) -> dict:
    assert resposta.status_code == 201, f"{resposta.request.method} {resposta.request.url.path}: {resposta.status_code} {resposta.text[:300]}"
    return resposta.json()


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ["TARGET_URL"].rstrip("/")


@pytest.fixture
def anonimo(base_url) -> Api:
    return Api(base_url)


@pytest.fixture(scope="session")
def bootstrap() -> dict[str, str]:
    return {k: os.environ[f"PUCK_BOOTSTRAP_{k.upper()}"] for k in ("nome", "email", "matricula", "senha")}


@pytest.fixture(scope="session")
def secretario(base_url, bootstrap) -> Api:
    api = Api(base_url)
    resposta = api.login(bootstrap["email"], bootstrap["matricula"], bootstrap["senha"])
    assert resposta.status_code == 200, f"login do secretário inicial falhou: {resposta.status_code} {resposta.text[:300]}"
    return api


class Fabrica:
    """Cria dados pelo próprio contrato, autenticada como secretário."""

    def __init__(self, secretario: Api, base_url: str):
        self.sec = secretario
        self.base_url = base_url

    def pessoa(self, perfil: str) -> Pessoa:
        nome = unico("Pessoa ")
        dados = {"nome": nome, "email": f"{unico('p')}@exemplo.test", "matricula": unico("M"),
                 "senha": "senha-sintetica-123"}
        corpo = criado(self.sec.post(f"/api/{perfil}", dados))
        return Pessoa(corpo["id"], nome, dados["email"], dados["matricula"], dados["senha"])

    def sessao(self, pessoa: Pessoa) -> Api:
        api = Api(self.base_url)
        resposta = api.login(pessoa.email, pessoa.matricula, pessoa.senha)
        assert resposta.status_code == 200, resposta.text[:300]
        return api

    def turma(self) -> int:
        curso = criado(self.sec.post("/api/cursos", {"nome": unico("Curso ")}))["id"]
        serie = criado(self.sec.post("/api/series", {"nome": unico("Serie ")}))["id"]
        return criado(self.sec.post("/api/turmas", {"ano": "2026", "curso_id": curso, "serie_id": serie}))["id"]

    def disciplina(self, turma: int, professor: Pessoa, carga_horaria: int = 80) -> int:
        corpo = {"nome": unico("Disciplina "), "professor_id": professor.id, "carga_horaria": carga_horaria}
        return criado(self.sec.post(f"/api/turmas/{turma}/disciplinas", corpo))["id"]

    def matricular(self, turma: int, aluno: Pessoa) -> None:
        criado(self.sec.post(f"/api/turmas/{turma}/matriculas", {"aluno_id": aluno.id}))


@pytest.fixture(scope="session")
def fabrica(secretario, base_url) -> Fabrica:
    return Fabrica(secretario, base_url)


# ---------------------------------------------------------------- métricas para o harness

_resultados: Counter = Counter()


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        area = Path(report.nodeid.split("::")[0]).stem.removeprefix("test_")
        _resultados[(area, report.outcome)] += 1


def pytest_terminal_summary(terminalreporter):
    areas = sorted({area for area, _ in _resultados})
    for area in areas:
        total = sum(n for (a, _), n in _resultados.items() if a == area)
        falhas = total - _resultados[(area, "passed")]
        terminalreporter.write_line(f"PUCK_METRIC oraculo_{area}_total {total}")
        terminalreporter.write_line(f"PUCK_METRIC oraculo_{area}_falhas {falhas}")
    total = sum(_resultados.values())
    terminalreporter.write_line(f"PUCK_METRIC oraculo_total {total}")
    terminalreporter.write_line(
        f"PUCK_METRIC oraculo_falhas {total - sum(n for (_, o), n in _resultados.items() if o == 'passed')}"
    )
