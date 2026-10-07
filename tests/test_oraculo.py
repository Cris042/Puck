"""Validade do oráculo (etapa 1): dourado íntegro, regra coerente e mutações detectadas."""

import collections
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATASET = json.loads((ROOT / "oracle/dataset/notas-dourado.json").read_text(encoding="utf-8"))
BOOTSTRAP = {"NOME": "Secretaria", "EMAIL": "sec@exemplo.test", "MATRICULA": "S1",
             "SENHA": "senha-inicial-123"}


def _referencia():
    spec = importlib.util.spec_from_file_location("referencia", ROOT / "oracle/referencia/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dataset_is_intact_and_covers_every_situation():
    conteudo = json.dumps(DATASET["casos"], ensure_ascii=False, indent=2, sort_keys=True)
    assert hashlib.sha256(conteudo.encode()).hexdigest() == DATASET["casos_sha256"]
    assert DATASET["fonte"]["sha"] == "ac48dc552b817233547104a5d0acba932d41ab91"
    situacoes = collections.Counter(c["esperado"]["situacao"] for c in DATASET["casos"])
    assert set(situacoes) == {"cursando", "aprovado", "reprovado", "reprovado_por_faltas"}
    # A peculiaridade mais importante do legado precisa de vários casos: média ≥ 60 + faltas.
    ordem = [c for c in DATASET["casos"] if c["esperado"]["situacao"] == "aprovado" and c["faltas"]]
    assert len(ordem) >= 4


def test_documented_rule_reproduces_every_legacy_result():
    """A regra escrita nos requisitos, reimplementada à parte, bate com o legado executado."""
    situacao = _referencia().situacao

    def numero(v):
        return None if v in (None, "") else float(v)

    for caso in DATASET["casos"]:
        notas = [None if numero(v) is None else min(numero(v), 100) for v in caso["notas"]]
        recs = [None if numero(v) is None else min(numero(v), 60) for v in caso["recuperacoes"]]
        media, parcial, sit = situacao(notas, recs, sum(caso["faltas"]), caso["carga_horaria"])
        esperado = caso["esperado"]
        assert (round(media, 6), round(parcial, 6), sit) == (
            round(esperado["media"], 6), round(esperado["media_parcial"], 6), esperado["situacao"]
        ), caso["id"]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _rodar_oraculo(mutacao: str) -> subprocess.CompletedProcess:
    porta = _porta_livre()
    env = {**os.environ, "PORT": str(porta), "PUCK_MUTACAO": mutacao,
           **{f"APP_BOOTSTRAP_{k}": v for k, v in BOOTSTRAP.items()}}
    app = subprocess.Popen([sys.executable, str(ROOT / "oracle/referencia/app.py")], env=env)
    try:
        for _ in range(50):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", porta)) == 0:
                    break
            time.sleep(0.1)
        env_oraculo = {**os.environ, "TARGET_URL": f"http://127.0.0.1:{porta}",
                       **{f"PUCK_BOOTSTRAP_{k}": v for k, v in BOOTSTRAP.items()}}
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(ROOT / "oracle/suite")],
            env=env_oraculo, capture_output=True, text=True, check=False, timeout=600,
        )
    finally:
        app.terminate()
        app.wait()


def test_reference_passes_the_whole_oracle():
    resultado = _rodar_oraculo("")
    assert resultado.returncode == 0, resultado.stdout[-3000:]
    assert "PUCK_METRIC oraculo_falhas 0" in resultado.stdout


@pytest.mark.parametrize(
    ("mutacao", "area"),
    [("ordem_faltas", "regra_notas"), ("limite_rec", "regra_notas"),
     ("media_parcial", "regra_notas"), ("autorizacao", "autorizacao"),
     ("resposta_login", "autenticacao"), ("logout", "autenticacao")],
)
def test_oracle_detects_each_deliberate_rule_break(mutacao: str, area: str):
    resultado = _rodar_oraculo(mutacao)
    assert resultado.returncode != 0, f"mutação {mutacao} passou despercebida"
    assert f"PUCK_METRIC oraculo_{area}_falhas 0" not in resultado.stdout


def test_contamination_probe_flags_canaries_and_copied_code(tmp_path: Path):
    from atena_benchmark.contaminacao import SONDAS, avaliar, resumo

    legado = tmp_path / "atena"
    (legado / "Models/ajax").mkdir(parents=True)
    original = "<?php\n$sql = MySql::conectar()->prepare('UPDATE notas SET atasada_nota04 = 0 WHERE cod_professo = ?');\n"
    (legado / "Models/ajax/CadastroNotas.php").write_text(original)
    (legado / "Models/HomeMolde.php").write_text("<?php class HomeMolde {}\n")

    memorizado = avaliar(lambda prompt: original, legado, repeticoes=1, sondas=SONDAS[:1])
    limpo = avaliar(lambda prompt: "Não tenho acesso a esse repositório.", legado, repeticoes=1,
                    sondas=SONDAS[:1])
    assert resumo(memorizado)["codigo_notas"]["canarios"] == ["atasada_nota04", "cod_professo"]
    assert resumo(memorizado)["codigo_notas"]["max_cobertura_5gramas"] == 1.0
    assert resumo(limpo)["codigo_notas"] == {"canarios": [], "max_cobertura_5gramas": 0.0}
