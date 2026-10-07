"""RF-01 e base técnica 3.2: login por perfil, resposta única, sessão no servidor, cookie."""

import httpx
from conftest import Api, unico

PALAVRAS_PROIBIDAS = ("senha", "password", "hash", "pepper", "token")


def _chaves(valor) -> list[str]:
    if isinstance(valor, dict):
        return [k.lower() for k in valor] + [c for v in valor.values() for c in _chaves(v)]
    if isinstance(valor, list):
        return [c for v in valor for c in _chaves(v)]
    return []


def test_login_identifica_perfil_de_cada_tipo(fabrica):
    for perfil, esperado in (("alunos", "aluno"), ("professores", "professor"), ("secretarios", "secretario")):
        pessoa = fabrica.pessoa(perfil)
        api = fabrica.sessao(pessoa)
        sessao = api.get("/api/sessao")
        assert sessao.status_code == 200
        assert sessao.json()["perfil"] == esperado
        assert sessao.json()["matricula"] == pessoa.matricula


def test_credenciais_invalidas_tem_resposta_unica(fabrica, base_url):
    pessoa = fabrica.pessoa("alunos")
    tentativas = [
        (pessoa.email, pessoa.matricula, "senha-errada-123"),
        (pessoa.email, unico("M"), pessoa.senha),
        (f"{unico('x')}@exemplo.test", pessoa.matricula, pessoa.senha),
    ]
    respostas = [Api(base_url).login(*t) for t in tentativas]
    assert [r.status_code for r in respostas] == [401, 401, 401]
    corpos = [r.json() for r in respostas]
    assert all(c["erro"]["codigo"] == "credenciais_invalidas" for c in corpos)
    assert corpos[0] == corpos[1] == corpos[2], "a resposta não pode revelar qual campo errou"


def test_logout_invalida_a_sessao_no_servidor(fabrica, base_url):
    pessoa = fabrica.pessoa("professores")
    api = fabrica.sessao(pessoa)
    copia = Api(base_url)
    copia.http.cookies = httpx.Cookies(api.http.cookies)
    assert api.delete("/api/sessao").status_code == 204
    assert api.get("/api/sessao").status_code == 401
    assert copia.get("/api/sessao").status_code == 401, "cookie antigo continua válido após logout"


def test_cookie_de_sessao_tem_atributos_seguros(fabrica, base_url):
    pessoa = fabrica.pessoa("alunos")
    resposta = Api(base_url).login(pessoa.email, pessoa.matricula, pessoa.senha)
    cabecalhos = [v.lower() for v in resposta.headers.get_list("set-cookie")]
    assert cabecalhos, "login não emitiu cookie"
    assert any("httponly" in c and ("samesite=lax" in c or "samesite=strict" in c) for c in cabecalhos)
    assert all("samesite" in c for c in cabecalhos)


def test_limite_de_tentativas_de_login(fabrica, base_url):
    pessoa = fabrica.pessoa("alunos")
    status = [Api(base_url).login(pessoa.email, pessoa.matricula, "errada-12345").status_code
              for _ in range(7)]
    assert 429 in status, f"7 tentativas falhas sem 429: {status}"


def test_respostas_nao_expoem_segredos(fabrica, secretario):
    aluno = fabrica.pessoa("alunos")
    api = fabrica.sessao(aluno)
    for resposta in (api.get("/api/sessao"), api.get("/api/alunos/eu/boletim"), secretario.get("/api/cursos")):
        assert resposta.status_code == 200
        assert not [k for k in _chaves(resposta.json()) if any(p in k for p in PALAVRAS_PROIBIDAS)]
    corpo = secretario.post("/api/professores", {"nome": "Prof", "email": f"{unico('q')}@exemplo.test",
                                                  "matricula": unico("M"), "senha": "senha-sintetica-123"})
    assert corpo.status_code == 201
    assert not [k for k in _chaves(corpo.json()) if any(p in k for p in PALAVRAS_PROIBIDAS)]
