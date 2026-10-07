"""Cenário fixo das tarefas de usabilidade (protocolo 4.4), criado e verificado pelo contrato HTTP.

Determinístico: a gravação (avaliador humano) e a reexecução (harness) partem dos mesmos dados e
das mesmas credenciais. Biblioteca padrão apenas: roda dentro do container de usabilidade.
Os dados são sintéticos.
"""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.request

SENHA = "Usabilidade#2026"
SECRETARIO = {"NOME": "Secretaria Usabilidade", "EMAIL": "secretaria@escola.test",
              "MATRICULA": "S0001", "SENHA": SENHA}
PROFESSORA = {"nome": "Professora Ana Lima", "email": "ana.lima@escola.test", "matricula": "P0001"}
ALUNA_CONSULTA = {"nome": "Bruna Consulta", "email": "bruna@escola.test", "matricula": "A0031"}
ALUNO_NOVO = {"nome": "Carlos Novo", "email": "carlos@escola.test", "matricula": "A0040"}
ALUNOS = [{"nome": f"Aluno {i:02d}", "email": f"aluno{i:02d}@escola.test", "matricula": f"A{i:04d}"}
          for i in range(1, 31)]
# Tarefa 1: nota do 1º bimestre de Matemática de cada um dos 30 alunos, na ordem da lista.
NOTAS_TAREFA_1 = [55, 62, 71, 48, 90, 66, 73, 59, 81, 64, 77, 52, 69, 88, 60,
                  45, 93, 70, 58, 67, 74, 61, 85, 50, 79, 63, 68, 57, 91, 72]
NOTA_CONSULTA = 73  # tarefa 2: nota de Bruna em História, 1º bimestre


class Cliente:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.abridor = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def chamar(self, metodo: str, caminho: str, corpo: dict | None = None):
        dados = None if corpo is None else json.dumps(corpo).encode()
        pedido = urllib.request.Request(
            self.base + caminho, data=dados, method=metodo,
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.abridor.open(pedido, timeout=30) as resposta:
                texto = resposta.read().decode()
                return resposta.status, (json.loads(texto) if texto else None)
        except urllib.error.HTTPError as erro:
            return erro.code, None

    def exigir(self, metodo: str, caminho: str, corpo: dict | None = None, status: int = 201):
        obtido, resposta = self.chamar(metodo, caminho, corpo)
        if obtido != status:
            raise RuntimeError(f"{metodo} {caminho}: esperado {status}, veio {obtido}")
        return resposta

    def entrar(self, email: str, matricula: str, senha: str = SENHA):
        return self.exigir("POST", "/api/sessao", {"email": email, "matricula": matricula, "senha": senha}, 200)


def semear(base: str) -> dict:
    """Cria o cenário. Devolve os ids que a verificação usa."""
    sec = Cliente(base)
    sec.entrar(SECRETARIO["EMAIL"], SECRETARIO["MATRICULA"], SECRETARIO["SENHA"])
    curso = sec.exigir("POST", "/api/cursos", {"nome": "Ensino Médio"})["id"]
    serie = sec.exigir("POST", "/api/series", {"nome": "1º ano"})["id"]
    serie_b = sec.exigir("POST", "/api/series", {"nome": "2º ano"})["id"]
    turma = sec.exigir("POST", "/api/turmas", {"ano": "2026", "curso_id": curso, "serie_id": serie})["id"]
    turma_b = sec.exigir("POST", "/api/turmas", {"ano": "2026", "curso_id": curso, "serie_id": serie_b})["id"]
    professora = sec.exigir("POST", "/api/professores", {**PROFESSORA, "senha": SENHA})["id"]
    matematica = sec.exigir("POST", f"/api/turmas/{turma}/disciplinas",
                            {"nome": "Matemática", "professor_id": professora, "carga_horaria": 80})["id"]
    historia = sec.exigir("POST", f"/api/turmas/{turma_b}/disciplinas",
                          {"nome": "História", "professor_id": professora, "carga_horaria": 80})["id"]
    alunos = []
    for aluno in ALUNOS:
        aid = sec.exigir("POST", "/api/alunos", {**aluno, "senha": SENHA})["id"]
        sec.exigir("POST", f"/api/turmas/{turma}/matriculas", {"aluno_id": aid})
        alunos.append(aid)
    bruna = sec.exigir("POST", "/api/alunos", {**ALUNA_CONSULTA, "senha": SENHA})["id"]
    sec.exigir("POST", f"/api/turmas/{turma_b}/matriculas", {"aluno_id": bruna})
    carlos = sec.exigir("POST", "/api/alunos", {**ALUNO_NOVO, "senha": SENHA})["id"]

    prof = Cliente(base)
    prof.entrar(PROFESSORA["email"], PROFESSORA["matricula"])
    vazio = [None, None, None, None]
    prof.exigir("PUT", f"/api/disciplinas/{historia}/notas",
                {"lancamentos": [{"aluno_id": bruna, "notas": [NOTA_CONSULTA, None, None, None],
                                  "recuperacoes": vazio}]}, 200)
    return {"turma": turma, "matematica": matematica, "alunos": alunos, "carlos": carlos}


def verificar(base: str, ids: dict, tarefa: str, texto_final: str) -> bool:
    sec = Cliente(base)
    sec.entrar(SECRETARIO["EMAIL"], SECRETARIO["MATRICULA"], SECRETARIO["SENHA"])
    if tarefa == "tarefa-1":
        _, boletim = sec.chamar("GET", f"/api/disciplinas/{ids['matematica']}/boletim")
        notas = {linha["aluno_id"]: linha["notas"][0] for linha in (boletim or {}).get("alunos", [])}
        return all(notas.get(aid) == nota for aid, nota in zip(ids["alunos"], NOTAS_TAREFA_1, strict=True))
    if tarefa == "tarefa-2":
        return str(NOTA_CONSULTA) in texto_final
    if tarefa == "tarefa-3":
        _, boletim = sec.chamar("GET", f"/api/disciplinas/{ids['matematica']}/boletim")
        return any(linha["aluno_id"] == ids["carlos"] for linha in (boletim or {}).get("alunos", []))
    raise ValueError(f"tarefa desconhecida: {tarefa}")
