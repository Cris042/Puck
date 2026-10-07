"""Matriz de autorização (requisitos): negado por padrão, 403 sem efeito colateral."""

from conftest import unico

LANCAMENTO_ZERO = {"notas": [0, 0, 0, 0], "recuperacoes": [None, None, None, None]}


def test_sem_sessao_recebe_401(anonimo):
    assert anonimo.post("/api/cursos", {"nome": unico("Curso ")}).status_code == 401
    assert anonimo.get("/api/alunos/eu/boletim").status_code == 401
    assert anonimo.get("/api/sessao").status_code == 401


def test_aluno_nao_cadastra_e_nada_e_criado(fabrica, secretario):
    aluno = fabrica.sessao(fabrica.pessoa("alunos"))
    nome = unico("Curso proibido ")
    assert aluno.post("/api/cursos", {"nome": nome}).status_code == 403
    assert nome not in [c["nome"] for c in secretario.get("/api/cursos").json()]


def test_professor_nao_cadastra_turma_nem_pessoa(fabrica):
    professor = fabrica.sessao(fabrica.pessoa("professores"))
    assert professor.post("/api/turmas", {"ano": "2026", "curso_id": 1, "serie_id": 1}).status_code == 403
    novo = {"nome": "X", "email": f"{unico('y')}@exemplo.test", "matricula": unico("M"), "senha": "senha-123456"}
    assert professor.post("/api/alunos", novo).status_code == 403


def test_professor_so_lanca_e_ve_as_proprias_disciplinas(fabrica, secretario):
    turma = fabrica.turma()
    dono, outro = fabrica.pessoa("professores"), fabrica.pessoa("professores")
    disciplina = fabrica.disciplina(turma, dono)
    aluno = fabrica.pessoa("alunos")
    fabrica.matricular(turma, aluno)
    antes = secretario.get(f"/api/disciplinas/{disciplina}/boletim").json()

    intruso = fabrica.sessao(outro)
    corpo = {"lancamentos": [{"aluno_id": aluno.id, **LANCAMENTO_ZERO}]}
    assert intruso.put(f"/api/disciplinas/{disciplina}/notas", corpo).status_code == 403
    faltas = {"data": "2026-03-02", "bimestre": 1, "registros": [{"aluno_id": aluno.id, "faltas": 5}]}
    assert intruso.post(f"/api/disciplinas/{disciplina}/faltas", faltas).status_code == 403
    assert intruso.get(f"/api/disciplinas/{disciplina}/boletim").status_code == 403
    assert secretario.get(f"/api/disciplinas/{disciplina}/boletim").json() == antes, "403 com efeito colateral"

    assert fabrica.sessao(dono).get(f"/api/disciplinas/{disciplina}/boletim").status_code == 200


def test_aluno_ve_so_o_proprio_boletim(fabrica):
    turma = fabrica.turma()
    disciplina = fabrica.disciplina(turma, fabrica.pessoa("professores"))
    aluno = fabrica.pessoa("alunos")
    fabrica.matricular(turma, aluno)
    api = fabrica.sessao(aluno)
    assert api.get(f"/api/disciplinas/{disciplina}/boletim").status_code == 403
    proprio = api.get("/api/alunos/eu/boletim")
    assert proprio.status_code == 200
    assert {d["aluno_id"] for d in proprio.json()["disciplinas"]} == {aluno.id}


def test_professor_e_secretario_nao_tem_boletim_de_aluno(fabrica, secretario):
    assert fabrica.sessao(fabrica.pessoa("professores")).get("/api/alunos/eu/boletim").status_code == 403
    assert secretario.get("/api/alunos/eu/boletim").status_code == 403


def test_so_secretario_define_prazo(fabrica, secretario):
    professor = fabrica.sessao(fabrica.pessoa("professores"))
    assert professor.put("/api/prazos/1", {"data_limite": "2026-12-31"}).status_code == 403
    assert secretario.put("/api/prazos/1", {"data_limite": "2026-12-31"}).status_code == 200
