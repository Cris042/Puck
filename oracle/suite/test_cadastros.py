"""Cadastros, matrícula, faltas e erros do contrato HTTP."""

from conftest import unico


def test_duplicidades_sao_409(fabrica, secretario):
    nome = unico("Curso ")
    assert secretario.post("/api/cursos", {"nome": nome}).status_code == 201
    assert secretario.post("/api/cursos", {"nome": nome}).status_code == 409

    aluno = fabrica.pessoa("alunos")
    repetida = {"nome": "Outro", "email": f"{unico('z')}@exemplo.test", "matricula": aluno.matricula,
                "senha": "senha-sintetica-123"}
    assert secretario.post("/api/professores", repetida).status_code == 409, "matrícula única entre perfis"

    turma = fabrica.turma()
    assert secretario.post(f"/api/turmas/{turma}/matriculas", {"aluno_id": aluno.id}).status_code == 201
    assert secretario.post(f"/api/turmas/{turma}/matriculas", {"aluno_id": aluno.id}).status_code == 409


def test_turma_repetida_e_referencias_invalidas(secretario):
    curso = secretario.post("/api/cursos", {"nome": unico("Curso ")}).json()["id"]
    serie = secretario.post("/api/series", {"nome": unico("Serie ")}).json()["id"]
    turma = {"ano": "2026", "curso_id": curso, "serie_id": serie}
    assert secretario.post("/api/turmas", turma).status_code == 201
    assert secretario.post("/api/turmas", turma).status_code == 409
    assert secretario.post("/api/turmas", {**turma, "curso_id": 999_999_999}).status_code == 422
    assert secretario.post("/api/turmas/999999999/disciplinas",
                           {"nome": "X", "professor_id": 1, "carga_horaria": 80}).status_code == 404


def test_senha_curta_e_422(secretario):
    curta = {"nome": "A", "email": f"{unico('w')}@exemplo.test", "matricula": unico("M"), "senha": "1234567"}
    assert secretario.post("/api/alunos", curta).status_code == 422


def test_mutacao_sem_json_e_415(secretario):
    resposta = secretario.http.post("/api/cursos", data={"nome": unico("Curso ")},
                                    headers={"Accept": "application/json"})
    assert resposta.status_code == 415


def test_matricula_vale_para_disciplinas_criadas_depois(fabrica, secretario):
    turma = fabrica.turma()
    aluno = fabrica.pessoa("alunos")
    fabrica.matricular(turma, aluno)
    disciplina = fabrica.disciplina(turma, fabrica.pessoa("professores"))
    alunos = secretario.get(f"/api/disciplinas/{disciplina}/boletim").json()["alunos"]
    linha = next(a for a in alunos if a["aluno_id"] == aluno.id)
    assert linha["notas"] == [None, None, None, None]
    assert linha["situacao"] == "cursando" and linha["media"] == 0 and linha["faltas"] == 0


def test_faltas_se_acumulam(fabrica, secretario):
    turma = fabrica.turma()
    professor = fabrica.pessoa("professores")
    disciplina = fabrica.disciplina(turma, professor)
    aluno = fabrica.pessoa("alunos")
    fabrica.matricular(turma, aluno)
    api = fabrica.sessao(professor)
    for data, n in (("2026-03-02", 3), ("2026-03-09", 4)):
        corpo = {"data": data, "bimestre": 1, "registros": [{"aluno_id": aluno.id, "faltas": n}]}
        assert api.post(f"/api/disciplinas/{disciplina}/faltas", corpo).status_code == 201
    alunos = secretario.get(f"/api/disciplinas/{disciplina}/boletim").json()["alunos"]
    assert next(a for a in alunos if a["aluno_id"] == aluno.id)["faltas"] == 7


def test_lancamento_invalido_e_422(fabrica):
    turma = fabrica.turma()
    professor = fabrica.pessoa("professores")
    disciplina = fabrica.disciplina(turma, professor)
    matriculado, de_fora = fabrica.pessoa("alunos"), fabrica.pessoa("alunos")
    fabrica.matricular(turma, matriculado)
    api = fabrica.sessao(professor)
    vazio = [None, None, None, None]
    negativo = {"lancamentos": [{"aluno_id": matriculado.id, "notas": [-1, None, None, None], "recuperacoes": vazio}]}
    assert api.put(f"/api/disciplinas/{disciplina}/notas", negativo).status_code == 422
    fora = {"lancamentos": [{"aluno_id": de_fora.id, "notas": [70, None, None, None], "recuperacoes": vazio}]}
    assert api.put(f"/api/disciplinas/{disciplina}/notas", fora).status_code == 422
    curto = {"lancamentos": [{"aluno_id": matriculado.id, "notas": [70], "recuperacoes": vazio}]}
    assert api.put(f"/api/disciplinas/{disciplina}/notas", curto).status_code == 422
