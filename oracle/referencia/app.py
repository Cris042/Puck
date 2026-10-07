"""Implementação de referência do contrato HTTP — só para VALIDAR o oráculo (etapa 1 do protocolo).

Nunca é vista pelos agentes e não participa da campanha. Python com biblioteca padrão, estado em
memória: não compete com as stacks avaliadas. Hash de senha por scrypt (Argon2 não está na
biblioteca padrão; o oráculo HTTP não observa o algoritmo).

`PUCK_MUTACAO` quebra uma regra de propósito; com qualquer mutação o oráculo TEM de falhar:
  ordem_faltas       avalia faltas antes da média (inverte a ordem do legado)
  limite_rec         não limita a recuperação a 60
  media_parcial      divide a média parcial por 4 em vez dos bimestres lançados
  autorizacao        professor lança notas em disciplina alheia
  resposta_login     erro de login revela o campo errado
  logout             logout não invalida a sessão no servidor
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from collections import defaultdict, deque
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MUTACAO = os.environ.get("PUCK_MUTACAO", "")
LOCK = threading.Lock()


def _hash(senha: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(senha.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + digest.hex()


def _confere(senha: str, guardado: str) -> bool:
    salt, digest = guardado.split("$")
    return hmac.compare_digest(_hash(senha, bytes.fromhex(salt)).split("$")[1], digest)


class Estado:
    def __init__(self):
        self.seq = 0
        self.pessoas: dict[int, dict] = {}
        self.cursos: dict[int, str] = {}
        self.series: dict[int, str] = {}
        self.turmas: dict[int, dict] = {}
        self.disciplinas: dict[int, dict] = {}
        self.matriculas: set[tuple[int, int]] = set()
        self.notas: dict[tuple[int, int], dict] = {}
        self.faltas: dict[tuple[int, int], int] = defaultdict(int)
        self.prazos: dict[int, str] = {}
        self.sessoes: dict[str, int] = {}
        self.tentativas: dict[str, deque] = defaultdict(deque)

    def novo_id(self) -> int:
        self.seq += 1
        return self.seq


ESTADO = Estado()


def situacao(notas, recs, faltas: int, carga_horaria: int):
    """A regra do legado (Models/ajax/CadastroNotas.php), sobre valores já limitados."""
    efetivas, lancados = [], 0
    for nota, rec in zip(notas, recs, strict=True):
        if nota is None:
            efetivas.append(0)
            continue
        lancados += 1
        efetivas.append(rec if (nota < 60 and rec is not None and rec > nota) else nota)
    media = sum(efetivas) / 4
    divisor = 4 if MUTACAO == "media_parcial" else max(lancados, 1)
    media_parcial = sum(e for e, n in zip(efetivas, notas, strict=True) if n is not None) / divisor
    reprova_faltas = faltas * 3300 > carga_horaria * 3600 * 75 / 100
    if MUTACAO == "ordem_faltas" and reprova_faltas:
        return media, media_parcial, "reprovado_por_faltas"
    if media >= 60 and lancados == 4:
        return media, media_parcial, "aprovado"
    if reprova_faltas:
        return media, media_parcial, "reprovado_por_faltas"
    if media < 60 and lancados == 4:
        return media, media_parcial, "reprovado"
    return media, media_parcial, "cursando"


class Erro(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str = ""):
        self.status, self.codigo, self.mensagem = status, codigo, mensagem or codigo


def _bootstrap() -> None:
    if any(p["perfil"] == "secretario" for p in ESTADO.pessoas.values()):
        return
    nome = os.environ.get("APP_BOOTSTRAP_NOME")
    if not nome:
        return
    pid = ESTADO.novo_id()
    ESTADO.pessoas[pid] = {
        "id": pid, "perfil": "secretario", "nome": nome, "email": os.environ["APP_BOOTSTRAP_EMAIL"],
        "matricula": os.environ["APP_BOOTSTRAP_MATRICULA"],
        "hash": _hash(os.environ["APP_BOOTSTRAP_SENHA"]),
    }


ROTAS: list[tuple[str, re.Pattern, str]] = []


def rota(metodo: str, padrao: str):
    def registrar(func):
        ROTAS.append((metodo, re.compile("^" + re.sub(r"{(\w+)}", r"(?P<\1>\\d+)", padrao) + "$"),
                      func.__name__))
        return func
    return registrar


class Handler(BaseHTTPRequestHandler):
    server_version = "referencia"

    def log_message(self, *args):  # silencioso
        pass

    # ------------------------------------------------------------ infraestrutura

    def _responder(self, status: int, corpo=None, cookie: str | None = None):
        dados = b"" if corpo is None else json.dumps(corpo).encode()
        self.send_response(status)
        if corpo is not None:
            self.send_header("Content-Type", "application/json")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _corpo(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho and not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise Erro(415, "tipo_nao_suportado")
        try:
            return json.loads(self.rfile.read(tamanho) or b"{}")
        except json.JSONDecodeError as exc:
            raise Erro(400, "json_invalido") from exc

    def _formulario(self) -> dict[str, str]:
        tamanho = int(self.headers.get("Content-Length") or 0)
        dados = urllib.parse.parse_qs(self.rfile.read(tamanho).decode())
        return {k: v[0] for k, v in dados.items()}

    def _html(self, titulo: str, corpo: str, status: int = 200):
        pagina = (f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>{escape(titulo)}"
                  f"</title></head><body><h1>{escape(titulo)}</h1>{corpo}</body></html>").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(pagina)))
        self.end_headers()
        self.wfile.write(pagina)

    def _redirecionar(self, destino: str, cookie: str | None = None):
        self.send_response(303)
        self.send_header("Location", destino)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _token(self) -> str | None:
        for parte in (self.headers.get("Cookie") or "").split(";"):
            nome, _, valor = parte.strip().partition("=")
            if nome == "sessao":
                return valor
        return None

    def _usuario(self, *perfis: str) -> dict:
        pid = ESTADO.sessoes.get(self._token() or "")
        if pid is None:
            raise Erro(401, "nao_autenticado")
        pessoa = ESTADO.pessoas[pid]
        if perfis and pessoa["perfil"] not in perfis:
            raise Erro(403, "proibido")
        return pessoa

    def _despachar(self, metodo: str):
        caminho = self.path.split("?", 1)[0]
        for m, padrao, nome in ROTAS:
            achado = padrao.match(caminho)
            if m == metodo and achado:
                try:
                    with LOCK:
                        getattr(self, nome)(**{k: int(v) for k, v in achado.groupdict().items()})
                except Erro as erro:
                    self._responder(erro.status, {"erro": {"codigo": erro.codigo, "mensagem": erro.mensagem}})
                return
        self._responder(404, {"erro": {"codigo": "nao_encontrado", "mensagem": "rota inexistente"}})

    def do_GET(self):
        self._despachar("GET")

    def do_POST(self):
        self._despachar("POST")

    def do_PUT(self):
        self._despachar("PUT")

    def do_DELETE(self):
        self._despachar("DELETE")

    # ------------------------------------------------------------ rotas

    @rota("GET", "/saude")
    def saude(self):
        self._responder(200, {"status": "ok"})

    @rota("POST", "/api/sessao")
    def entrar(self):
        corpo = self._corpo()
        chave = f"{corpo.get('email')}|{self.client_address[0]}"
        janela = ESTADO.tentativas[chave]
        agora = time.monotonic()
        while janela and agora - janela[0] > 60:
            janela.popleft()
        if len(janela) >= 5:
            raise Erro(429, "muitas_tentativas")
        pessoa = next((p for p in ESTADO.pessoas.values() if p["email"] == corpo.get("email")), None)
        valido = (pessoa is not None and pessoa["matricula"] == corpo.get("matricula")
                  and _confere(str(corpo.get("senha", "")), pessoa["hash"]))
        if not valido:
            janela.append(agora)
            codigo = "credenciais_invalidas"
            if MUTACAO == "resposta_login":
                codigo = "usuario_inexistente" if pessoa is None else "senha_ou_matricula_errada"
            raise Erro(401, codigo, "credenciais inválidas")
        token = secrets.token_urlsafe(32)
        ESTADO.sessoes[token] = pessoa["id"]
        self._responder(200, _sessao(pessoa), cookie=f"sessao={token}; HttpOnly; SameSite=Lax; Path=/")

    @rota("GET", "/api/sessao")
    def sessao_atual(self):
        self._responder(200, _sessao(self._usuario()))

    @rota("DELETE", "/api/sessao")
    def sair(self):
        self._usuario()
        if MUTACAO != "logout":
            ESTADO.sessoes.pop(self._token(), None)
        self._responder(204, cookie="sessao=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/")

    def _nomeado(self, tabela: dict):
        self._usuario("secretario")
        nome = str(self._corpo().get("nome", "")).strip()
        if not nome:
            raise Erro(422, "nome_obrigatorio")
        if nome in tabela.values():
            raise Erro(409, "duplicado")
        nid = ESTADO.novo_id()
        tabela[nid] = nome
        self._responder(201, {"id": nid, "nome": nome})

    @rota("POST", "/api/cursos")
    def novo_curso(self):
        self._nomeado(ESTADO.cursos)

    @rota("GET", "/api/cursos")
    def cursos(self):
        self._usuario("secretario")
        self._responder(200, [{"id": i, "nome": n} for i, n in ESTADO.cursos.items()])

    @rota("POST", "/api/series")
    def nova_serie(self):
        self._nomeado(ESTADO.series)

    @rota("POST", "/api/turmas")
    def nova_turma(self):
        self._usuario("secretario")
        corpo = self._corpo()
        if corpo.get("curso_id") not in ESTADO.cursos or corpo.get("serie_id") not in ESTADO.series:
            raise Erro(422, "referencia_invalida")
        chave = (str(corpo.get("ano")), corpo["curso_id"], corpo["serie_id"])
        if any((t["ano"], t["curso_id"], t["serie_id"]) == chave for t in ESTADO.turmas.values()):
            raise Erro(409, "duplicada")
        tid = ESTADO.novo_id()
        ESTADO.turmas[tid] = {"id": tid, "ano": chave[0], "curso_id": chave[1], "serie_id": chave[2]}
        self._responder(201, ESTADO.turmas[tid])

    def _pessoa(self, perfil: str):
        self._usuario("secretario")
        corpo = self._corpo()
        if len(str(corpo.get("senha", ""))) < 8 or not corpo.get("nome") or "@" not in str(corpo.get("email", "")):
            raise Erro(422, "dados_invalidos")
        if any(p["matricula"] == corpo["matricula"] or p["email"] == corpo["email"]
               for p in ESTADO.pessoas.values()):
            raise Erro(409, "duplicada")
        pid = ESTADO.novo_id()
        ESTADO.pessoas[pid] = {"id": pid, "perfil": perfil, "nome": corpo["nome"],
                               "email": corpo["email"], "matricula": corpo["matricula"],
                               "hash": _hash(corpo["senha"])}
        self._responder(201, _publico(ESTADO.pessoas[pid]))

    @rota("POST", "/api/alunos")
    def novo_aluno(self):
        self._pessoa("aluno")

    @rota("POST", "/api/professores")
    def novo_professor(self):
        self._pessoa("professor")

    @rota("POST", "/api/secretarios")
    def novo_secretario(self):
        self._pessoa("secretario")

    @rota("POST", "/api/turmas/{turma_id}/disciplinas")
    def nova_disciplina(self, turma_id: int):
        self._usuario("secretario")
        corpo = self._corpo()
        if turma_id not in ESTADO.turmas:
            raise Erro(404, "turma_inexistente")
        professor = ESTADO.pessoas.get(corpo.get("professor_id"))
        ch = corpo.get("carga_horaria")
        if not professor or professor["perfil"] != "professor" or not isinstance(ch, int) or ch < 1:
            raise Erro(422, "dados_invalidos")
        if any(d["turma_id"] == turma_id and d["nome"] == corpo.get("nome") for d in ESTADO.disciplinas.values()):
            raise Erro(409, "duplicada")
        did = ESTADO.novo_id()
        ESTADO.disciplinas[did] = {"id": did, "nome": corpo["nome"], "turma_id": turma_id,
                                   "professor_id": professor["id"], "carga_horaria": ch}
        self._responder(201, ESTADO.disciplinas[did])

    @rota("POST", "/api/turmas/{turma_id}/matriculas")
    def matricular(self, turma_id: int):
        self._usuario("secretario")
        corpo = self._corpo()
        if turma_id not in ESTADO.turmas:
            raise Erro(404, "turma_inexistente")
        aluno = ESTADO.pessoas.get(corpo.get("aluno_id"))
        if not aluno or aluno["perfil"] != "aluno":
            raise Erro(422, "aluno_inexistente")
        if (turma_id, aluno["id"]) in ESTADO.matriculas:
            raise Erro(409, "ja_matriculado")
        ESTADO.matriculas.add((turma_id, aluno["id"]))
        self._responder(201, {"turma_id": turma_id, "aluno_id": aluno["id"]})

    @rota("PUT", "/api/prazos/{bimestre}")
    def prazo(self, bimestre: int):
        self._usuario("secretario")
        data = str(self._corpo().get("data_limite", ""))
        if not 1 <= bimestre <= 4 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
            raise Erro(422, "dados_invalidos")
        ESTADO.prazos[bimestre] = data
        self._responder(200, {"bimestre": bimestre, "data_limite": data})

    def _disciplina_do_professor(self, disciplina_id: int) -> dict:
        professor = self._usuario("professor")
        disciplina = ESTADO.disciplinas.get(disciplina_id)
        if not disciplina:
            raise Erro(404, "disciplina_inexistente")
        if disciplina["professor_id"] != professor["id"] and MUTACAO != "autorizacao":
            raise Erro(403, "proibido")
        return disciplina

    @rota("PUT", "/api/disciplinas/{disciplina_id}/notas")
    def lancar(self, disciplina_id: int):
        disciplina = self._disciplina_do_professor(disciplina_id)
        lancamentos = self._corpo().get("lancamentos")
        if not isinstance(lancamentos, list):
            raise Erro(422, "dados_invalidos")
        validados = []
        for item in lancamentos:
            notas, recs = item.get("notas"), item.get("recuperacoes")
            if (not isinstance(notas, list) or not isinstance(recs, list) or len(notas) != 4
                    or len(recs) != 4 or (disciplina["turma_id"], item.get("aluno_id")) not in ESTADO.matriculas
                    or any(v is not None and (not isinstance(v, int | float) or v < 0) for v in notas + recs)):
                raise Erro(422, "lancamento_invalido")
            limite_rec = 10**9 if MUTACAO == "limite_rec" else 60
            validados.append((item["aluno_id"], [None if v is None else min(v, 100) for v in notas],
                              [None if v is None else min(v, limite_rec) for v in recs]))
        for aluno_id, notas, recs in validados:
            ESTADO.notas[(disciplina_id, aluno_id)] = {"notas": notas, "recuperacoes": recs}
        self._responder(200, {"atualizados": len(validados)})

    @rota("POST", "/api/disciplinas/{disciplina_id}/faltas")
    def faltas(self, disciplina_id: int):
        disciplina = self._disciplina_do_professor(disciplina_id)
        corpo = self._corpo()
        registros = corpo.get("registros")
        if not isinstance(registros, list) or corpo.get("bimestre") not in (1, 2, 3, 4):
            raise Erro(422, "dados_invalidos")
        for registro in registros:
            n = registro.get("faltas")
            if (not isinstance(n, int) or n < 0
                    or (disciplina["turma_id"], registro.get("aluno_id")) not in ESTADO.matriculas):
                raise Erro(422, "dados_invalidos")
        for registro in registros:
            ESTADO.faltas[(disciplina_id, registro["aluno_id"])] += registro["faltas"]
        self._responder(201, {"registrados": len(registros)})

    @rota("GET", "/api/disciplinas/{disciplina_id}/boletim")
    def boletim(self, disciplina_id: int):
        usuario = self._usuario("professor", "secretario")
        disciplina = ESTADO.disciplinas.get(disciplina_id)
        if not disciplina:
            raise Erro(404, "disciplina_inexistente")
        if usuario["perfil"] == "professor" and disciplina["professor_id"] != usuario["id"]:
            raise Erro(403, "proibido")
        alunos = [_linha(disciplina, aid) for (tid, aid) in sorted(ESTADO.matriculas)
                  if tid == disciplina["turma_id"]]
        self._responder(200, {"disciplina": disciplina, "alunos": alunos})

    @rota("GET", "/api/alunos/eu/boletim")
    def meu_boletim(self):
        aluno = self._usuario("aluno")
        linhas = []
        for disciplina in ESTADO.disciplinas.values():
            if (disciplina["turma_id"], aluno["id"]) in ESTADO.matriculas:
                linha = _linha(disciplina, aluno["id"])
                linhas.append({**linha, "disciplina_id": disciplina["id"], "disciplina_nome": disciplina["nome"]})
        self._responder(200, {"disciplinas": linhas})


class Telas(Handler):
    """Interface HTML mínima da referência: só para validar o pipeline de usabilidade."""

    @rota("GET", "/")
    def tela_entrar(self):
        self._html("Entrar", "<form method='post' action='/entrar'>"
                   "<label>E-mail <input name='email'></label>"
                   "<label>Matrícula <input name='matricula'></label>"
                   "<label>Senha <input name='senha' type='password'></label>"
                   "<button>Entrar</button></form>")

    @rota("POST", "/entrar")
    def tela_entrar_enviar(self):
        dados = self._formulario()
        pessoa = next((p for p in ESTADO.pessoas.values() if p["email"] == dados.get("email")), None)
        if not pessoa or pessoa["matricula"] != dados.get("matricula") or not _confere(dados.get("senha", ""), pessoa["hash"]):
            return self._html("Entrar", "<p>Credenciais inválidas</p>", 401)
        token = secrets.token_urlsafe(32)
        ESTADO.sessoes[token] = pessoa["id"]
        self._redirecionar("/inicio", f"sessao={token}; HttpOnly; SameSite=Lax; Path=/")

    @rota("GET", "/inicio")
    def tela_inicio(self):
        pessoa = self._usuario()
        if pessoa["perfil"] == "professor":
            itens = "".join(f"<li><a href='/disciplinas/{d['id']}/notas'>{escape(d['nome'])}</a></li>"
                            for d in ESTADO.disciplinas.values() if d["professor_id"] == pessoa["id"])
            return self._html("Minhas disciplinas", f"<ul>{itens}</ul>")
        if pessoa["perfil"] == "aluno":
            linhas = "".join(
                f"<tr><td>{escape(d['nome'])}</td><td>{_linha(d, pessoa['id'])['notas'][0]}</td>"
                f"<td>{_linha(d, pessoa['id'])['situacao']}</td></tr>"
                for d in ESTADO.disciplinas.values() if (d["turma_id"], pessoa["id"]) in ESTADO.matriculas)
            return self._html("Meu boletim", f"<table><tr><th>Disciplina</th><th>1º bimestre</th>"
                              f"<th>Situação</th></tr>{linhas}</table>")
        turmas = "".join(f"<option value='{t['id']}'>{t['ano']} - {escape(ESTADO.cursos[t['curso_id']])} - "
                         f"{escape(ESTADO.series[t['serie_id']])}</option>" for t in ESTADO.turmas.values())
        alunos = "".join(f"<option value='{p['id']}'>{escape(p['nome'])}</option>"
                         for p in ESTADO.pessoas.values() if p["perfil"] == "aluno")
        self._html("Matrícula", "<form method='post' action='/matriculas'>"
                   f"<label>Turma <select name='turma_id'>{turmas}</select></label>"
                   f"<label>Aluno <select name='aluno_id'>{alunos}</select></label>"
                   "<button>Matricular</button></form>")

    @rota("GET", "/disciplinas/{disciplina_id}/notas")
    def tela_notas(self, disciplina_id: int):
        disciplina = self._disciplina_do_professor(disciplina_id)
        linhas = "".join(
            f"<tr><td>{escape(ESTADO.pessoas[aid]['nome'])}</td><td><input name='nota_{aid}' "
            f"aria-label='Nota de {escape(ESTADO.pessoas[aid]['nome'])}'></td></tr>"
            for (tid, aid) in sorted(ESTADO.matriculas) if tid == disciplina["turma_id"])
        self._html(f"Notas do 1º bimestre - {disciplina['nome']}",
                   f"<form method='post'><table>{linhas}</table><button>Salvar</button></form>")

    @rota("POST", "/disciplinas/{disciplina_id}/notas")
    def tela_notas_enviar(self, disciplina_id: int):
        self._disciplina_do_professor(disciplina_id)
        for chave, valor in self._formulario().items():
            if chave.startswith("nota_") and valor.strip():
                registro = ESTADO.notas.setdefault((disciplina_id, int(chave[5:])),
                                                   {"notas": [None] * 4, "recuperacoes": [None] * 4})
                registro["notas"][0] = min(float(valor) if "." in valor else int(valor), 100)
        self._html("Notas salvas", "<p>Notas salvas.</p><a href='/inicio'>Voltar</a>")

    @rota("POST", "/matriculas")
    def tela_matricular(self):
        self._usuario("secretario")
        dados = self._formulario()
        ESTADO.matriculas.add((int(dados["turma_id"]), int(dados["aluno_id"])))
        self._html("Matrícula feita", "<p>Matrícula feita.</p>")


def _publico(pessoa: dict) -> dict:
    return {k: pessoa[k] for k in ("id", "nome", "email", "matricula")}


def _sessao(pessoa: dict) -> dict:
    return {"perfil": pessoa["perfil"], "nome": pessoa["nome"], "matricula": pessoa["matricula"]}


def _linha(disciplina: dict, aluno_id: int) -> dict:
    lancado = ESTADO.notas.get((disciplina["id"], aluno_id), {"notas": [None] * 4, "recuperacoes": [None] * 4})
    faltas = ESTADO.faltas[(disciplina["id"], aluno_id)]
    media, parcial, sit = situacao(lancado["notas"], lancado["recuperacoes"], faltas, disciplina["carga_horaria"])
    aluno = ESTADO.pessoas[aluno_id]
    return {"aluno_id": aluno_id, "nome": aluno["nome"], "matricula": aluno["matricula"],
            "notas": lancado["notas"], "recuperacoes": lancado["recuperacoes"], "faltas": faltas,
            "media": media, "media_parcial": parcial, "situacao": sit}


def main() -> None:
    _bootstrap()
    porta = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", porta), Telas).serve_forever()


if __name__ == "__main__":
    main()
