"""Dataset dourado da regra de notas, produzido EXECUTANDO o Atena legado no SHA fixado.

Nada da regra é reimplementado aqui: cada caso vira um POST no endpoint real do legado
(`Models/ajax/CadastroNotas.php`, PHP 7.3) e o resultado é lido do banco que ele gravou. O oráculo
das reescritas compara contra esse arquivo.

Executado uma vez antes da campanha (etapa 1 do protocolo); duas execuções devem produzir o mesmo
arquivo (`sha256` registrado no próprio dataset).
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from .workspace import export_tree

LEGACY_IMAGE = "puck-atena-legado"
MARIADB_IMAGE = "mariadb:10.4"
SEED = 2026
CURSO = "Curso Dourado"
SERIE = "1 Ano"
PROFESSOR = "9001"
DISCIPLINA = "Matematica"
SITUACOES = {"0": "cursando", "1": "aprovado", "3": "reprovado_por_faltas", "4": "reprovado"}


@dataclass(frozen=True)
class Caso:
    id: str
    carga_horaria: int
    faltas: list[int]  # um lançamento de presença por item (o legado soma)
    notas: list[str | None]  # 4 bimestres; None = não lançada
    recuperacoes: list[str | None]
    descricao: str = ""


def _c(cid, ch, faltas, notas, recs, descricao) -> Caso:
    return Caso(cid, ch, faltas, notas, recs, descricao)


N = None

# Limite de faltas: faltas × 3300 > CH × 3600 × 75% ⇔ faltas > CH × 0,8181… (CH=80 → 66 reprova).
CASOS_BORDA: list[Caso] = [
    _c("B01", 80, [], ["70", "80", "90", "60"], [N] * 4, "4 bimestres, média ≥ 60"),
    _c("B02", 80, [], ["60", "60", "60", "60"], [N] * 4, "média exatamente 60"),
    _c("B03", 80, [], ["59", "60", "60", "60"], [N] * 4, "média 59,75 com 4 bimestres"),
    _c("B04", 80, [], ["40", "80", "80", "80"], ["55", N, N, N], "rec > nota < 60 substitui"),
    _c("B05", 80, [], ["40", "80", "80", "80"], ["30", N, N, N], "rec < nota não substitui"),
    _c("B06", 80, [], ["40", "80", "80", "80"], ["95", N, N, N], "rec acima de 60 é limitada a 60"),
    _c("B07", 80, [], ["150", "50", "50", "50"], [N] * 4, "nota acima de 100 é limitada a 100"),
    _c("B08", 80, [], ["60", "60", "60", "60"], ["90", "90", "90", "90"], "nota ≥ 60 ignora rec"),
    _c("B09", 80, [], ["70", "80", N, N], [N] * 4, "2 bimestres: cursando"),
    _c("B10", 80, [], [N, N, N, N], [N] * 4, "nada lançado"),
    _c("B11", 80, [], ["0", "0", "0", "0"], [N] * 4, "zero lançado ≠ vazio"),
    _c("B12", 80, [70], ["70", "70", "70", "70"], [N] * 4, "faltas acima com média ≥ 60: aprova"),
    _c("B13", 80, [70], ["40", "40", "40", "40"], [N] * 4, "faltas acima com média < 60"),
    _c("B14", 80, [70], ["40", "40", N, N], [N] * 4, "faltas acima, 2 bimestres"),
    _c("B15", 80, [65], ["40", "40", N, N], [N] * 4, "65 faltas: abaixo do limite"),
    _c("B16", 80, [66], ["40", "40", N, N], [N] * 4, "66 faltas: acima do limite"),
    _c("B17", 80, [30, 20, 16], ["40", N, N, N], [N] * 4, "faltas somadas de 3 registros"),
    _c("B18", 80, [], ["59.5", "60", "60", "60"], ["60", N, N, N], "nota decimal com rec"),
    _c("B19", 80, [], ["33", "33", "34", N], [N] * 4, "média parcial não inteira"),
    _c("B20", 80, [], [N, "100", N, "20"], [N, N, N, "59"], "bimestres alternados"),
    _c("B21", 80, [], [N, N, N, N], ["50", "50", "50", "50"], "rec sem nota é ignorada"),
    _c("B22", 40, [33], ["30", N, N, N], [N] * 4, "CH 40: 33 faltas acima do limite"),
    _c("B23", 40, [32], ["30", N, N, N], [N] * 4, "CH 40: 32 faltas abaixo do limite"),
    _c("B24", 120, [99], ["30", "30", "30", "30"], [N] * 4, "CH 120: 99 faltas, média < 60"),
    _c("B25", 80, [70], ["60", "60", "60", "60"], [N] * 4, "faltas acima, média exatamente 60: aprova"),
    _c("B26", 40, [40], ["100", "90", "80", "70"], [N] * 4, "CH 40, 40 faltas, média 85: aprova"),
    _c("B27", 120, [150], ["50", "70", "70", "70"], ["60", N, N, N], "rec leva a média a 67,5 com faltas acima"),
    _c("B28", 80, [70], ["59", "60", "60", "60"], [N] * 4, "faltas acima, média 59,75: reprova por faltas"),
]


def _nota(rng: random.Random, maximo: int = 110) -> str | None:
    sorteio = rng.random()
    if sorteio < 0.15:
        return None
    if sorteio < 0.25:
        return f"{rng.randint(0, maximo * 10) / 10:g}"
    return str(rng.randint(0, maximo))


def casos_aleatorios(quantidade: int = 120, seed: int = SEED) -> list[Caso]:
    rng = random.Random(seed)
    casos = []
    for i in range(quantidade):
        ch = rng.choice([40, 80, 120])
        limite = int(ch * 2700 / 3300)
        faltas = [rng.randint(0, limite + 10)] if rng.random() < 0.6 else []
        notas = [_nota(rng) for _ in range(4)]
        recs = [_nota(rng, 80) if rng.random() < 0.4 else None for _ in range(4)]
        casos.append(Caso(f"A{i + 1:03d}", ch, faltas, notas, recs, "aleatório"))
    return casos


def todos_os_casos() -> list[Caso]:
    return CASOS_BORDA + casos_aleatorios()


def _sh(*args: str, check: bool = True, input_text: str | None = None) -> str:
    completed = subprocess.run(args, text=True, capture_output=True, input=input_text, check=False)
    if check and completed.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:4])}…: {completed.stderr.strip()[-2000:]}")
    return completed.stdout


def _sql_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


class LegadoEmExecucao:
    """MariaDB + Apache/PHP 7.3 com o código do legado montado sem modificação."""

    def __init__(self, legacy_dir: Path, schema: Path):
        self.legacy_dir = legacy_dir
        self.schema = schema
        self.name = f"puck-legado-{uuid.uuid4().hex[:8]}"
        self.socket_volume = f"{self.name}-socket"
        self.port = ""

    def __enter__(self) -> LegadoEmExecucao:
        _sh("docker", "volume", "create", self.socket_volume)
        _sh("docker", "run", "-d", "--name", f"{self.name}-db", "-e",
            "MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1", "-e", "MARIADB_DATABASE=SistemaEscolar",
            "-v", f"{self.socket_volume}:/run/mysqld", "--tmpfs", "/var/lib/mysql", MARIADB_IMAGE)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            ok = subprocess.run(
                ["docker", "exec", f"{self.name}-db", "mysql", "-uroot", "-e",
                 "SELECT 1", "SistemaEscolar"], capture_output=True, check=False,
            )
            if ok.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("MariaDB não ficou pronto")
        self.mysql(self.schema.read_text(encoding="utf-8"))
        _sh("docker", "run", "-d", "--name", f"{self.name}-php", "-p", "127.0.0.1::80",
            "-v", f"{self.legacy_dir}:/var/www/html:ro", "-v", f"{self.socket_volume}:/run/mysqld",
            LEGACY_IMAGE)
        self.port = _sh("docker", "port", f"{self.name}-php", "80").strip().rsplit(":", 1)[-1]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{self.port}/", timeout=2)
                return self
            except httpx.HTTPError:
                time.sleep(0.5)
        raise RuntimeError("Apache do legado não respondeu")

    def __exit__(self, *exc) -> None:
        for suffix in ("php", "db"):
            subprocess.run(["docker", "rm", "-f", "-v", f"{self.name}-{suffix}"],
                           capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", "-f", self.socket_volume],
                       capture_output=True, check=False)

    def mysql(self, sql: str) -> str:
        return _sh("docker", "exec", "-i", f"{self.name}-db", "mysql", "-uroot", "--batch",
                   "--skip-column-names", "SistemaEscolar", input_text=sql)

    def post(self, path: str, data: dict[str, str]) -> httpx.Response:
        return httpx.post(f"http://127.0.0.1:{self.port}/{path}", data=data, timeout=60)


def _turma(ch: int) -> tuple[str, str, str]:
    """Uma turma por carga horária: o legado lê a CH da disciplina do professor na turma."""
    return CURSO, SERIE, f"2026-CH{ch}"


def _matricula(indice: int) -> str:
    # Numérica: o legado interpola `cod_aluno = $aluno` sem aspas no UPDATE.
    return f"26{indice:05d}"


def executar_casos(legado: LegadoEmExecucao, casos: list[Caso]) -> dict[str, dict]:
    matriculas = {caso.id: _matricula(i + 1) for i, caso in enumerate(casos)}
    for ch in sorted({c.carga_horaria for c in casos}):
        curso, serie, ano = _turma(ch)
        grupo = [c for c in casos if c.carga_horaria == ch]
        rows = [
            "INSERT INTO diciplina VALUES (null, {}, {}, {}, {}, {}, {});".format(
                *map(_sql_literal, (DISCIPLINA, ano, curso, serie, PROFESSOR, str(ch)))
            )
        ]
        for caso in grupo:
            m = matriculas[caso.id]
            rows.append("INSERT INTO matriculados VALUES (null, {}, {}, {}, {}, {}, 1);".format(
                *map(_sql_literal, (curso, serie, ano, m, f"Aluno {caso.id}"))))
            for falta in caso.faltas:
                rows.append("INSERT INTO presenca VALUES (null, {}, {}, {}, {}, {}, {}, {}, {}, {});"
                            .format(*map(_sql_literal, (m, PROFESSOR, curso, serie, ano, DISCIPLINA,
                                                        str(falta), "2026-03-01", "1"))))
        legado.mysql("\n".join(rows))

        form = {"cod_serie": serie, "cod_curso": curso, "cod_ano": ano, "professo": PROFESSOR,
                "nome_diciplina": DISCIPLINA, "salva": "1"}
        for caso in grupo:
            m = matriculas[caso.id]
            for b in range(4):
                form[f"nota0{b + 1}{m}"] = caso.notas[b] or ""
                form[f"rec0{b + 1}{m}"] = caso.recuperacoes[b] or ""
        resposta = legado.post("Models/ajax/CadastroNotas.php", form)
        if resposta.status_code != 200 or '"sucesso":true' not in resposta.text:
            raise RuntimeError(f"legado respondeu {resposta.status_code}: {resposta.text[:500]}")

    linhas = legado.mysql(
        "SELECT cod_aluno, n1, r1, n2, r2, n3, r3, n4, r4, media, media_parcial, aprovado "
        "FROM notas ORDER BY cod_aluno;"
    )
    gravado = {}
    for linha in linhas.splitlines():
        campos = linha.split("\t")
        gravado[campos[0]] = campos[1:]
    resultado = {}
    for caso in casos:
        campos = gravado[matriculas[caso.id]]
        resultado[caso.id] = {
            "notas_gravadas": [campos[0], campos[2], campos[4], campos[6]],
            "recuperacoes_gravadas": [campos[1], campos[3], campos[5], campos[7]],
            "media": float(campos[8]),
            "media_parcial": float(campos[9]),
            "situacao": SITUACOES[campos[10]],
            "situacao_codigo_legado": int(campos[10]),
        }
    return resultado


def gerar_dourado(atena_repo: str, ref: str, schema: Path, saida: Path) -> dict:
    casos = todos_os_casos()
    with tempfile.TemporaryDirectory(prefix="puck-legado-") as tmp:
        legacy_dir = Path(tmp) / "atena"
        sha = export_tree(atena_repo, ref, legacy_dir)
        with LegadoEmExecucao(legacy_dir, schema) as legado:
            resultados = executar_casos(legado, casos)
    imagens = {
        image: _sh("docker", "image", "inspect", image, "--format",
                   "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}").strip()
        for image in (LEGACY_IMAGE, MARIADB_IMAGE)
    }
    corpo = [
        {**asdict(caso), "esperado": resultados[caso.id]} for caso in casos
    ]
    conteudo = json.dumps(corpo, ensure_ascii=False, indent=2, sort_keys=True)
    dataset = {
        "descricao": "Regra de notas do Atena legado, obtida executando o código no SHA fixado.",
        "fonte": {"repositorio": atena_repo, "sha": sha,
                  "endpoint": "Models/ajax/CadastroNotas.php", "imagens": imagens},
        "suposicoes": [
            "colunas de notas como texto: o valor gravado é o calculado pelo PHP (tipo real de 2024 desconhecido)",
            "uma disciplina por professor por turma: o legado lê a carga horária da primeira disciplina do professor na turma",
        ],
        "casos_sha256": hashlib.sha256(conteudo.encode()).hexdigest(),
        "casos": corpo,
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(dataset, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                     encoding="utf-8")
    return dataset
