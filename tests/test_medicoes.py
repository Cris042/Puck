"""Fase F: SAST, dependências, DAST, carga e usabilidade."""

import json
import os
import shutil
from pathlib import Path

import pytest

from atena_benchmark.medicoes import (
    contar_composer_audit,
    contar_govulncheck,
    contar_semgrep,
    contar_zap,
    dast,
    sast,
)
from atena_benchmark.usabilidade import klm, pontuar

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
DOCKER = pytest.mark.skipif(
    os.environ.get("PUCK_DOCKER_TESTS") != "1",
    reason="testes com Docker: PUCK_DOCKER_TESTS=1 (e `atena-bench sandbox build-images`)",
)


def test_semgrep_counts_by_rule():
    saida = json.dumps({"results": [{"check_id": "rules.sql-interpolado"},
                                    {"check_id": "rules.sql-interpolado"},
                                    {"check_id": "rules.hash-senha-fraco"}],
                        "errors": [{}]})
    assert contar_semgrep(saida) == {"sast_sql_interpolado": 2, "sast_hash_senha_fraco": 1,
                                     "sast_total": 3, "sast_erros_varredura": 1}


def test_govulncheck_counts_reachable_apart_from_imported():
    stream = "\n".join(json.dumps(o, indent=2) for o in [
        {"config": {"scanner_name": "govulncheck"}},
        {"finding": {"osv": "GO-1", "trace": [{"module": "m", "function": "F"}]}},
        {"finding": {"osv": "GO-1", "trace": [{"module": "m", "function": "G"}]}},
        {"finding": {"osv": "GO-2", "trace": [{"module": "m", "package": "p"}]}},
    ])
    assert contar_govulncheck(stream) == {"deps_vulnerabilidades": 2, "deps_alcancaveis": 1}


def test_composer_audit_counts_advisories():
    saida = json.dumps({"advisories": {"a/b": [{}, {}], "c/d": [{}]}, "abandoned": []})
    assert contar_composer_audit(saida)["deps_vulnerabilidades"] == 3
    assert contar_composer_audit(json.dumps({"advisories": []}))["deps_vulnerabilidades"] == 0


def test_zap_counts_alerts_by_risk():
    relatorio = {"site": [{"alerts": [{"riskcode": "3"}, {"riskcode": "1"}, {"riskcode": "1"}]}]}
    assert contar_zap(relatorio) == {"dast_alto": 1, "dast_medio": 0, "dast_baixo": 2, "dast_info": 0}


ROTEIRO = '''
def run(playwright):
    page = context.new_page()
    page.goto("http://localhost:8080/")
    page.get_by_label("E-mail").click()
    page.get_by_label("E-mail").fill("ab")
    page.get_by_label("E-mail").press("Tab")
    page.get_by_label("Senha").fill("cd")
    page.get_by_label("Senha").press("Enter")
    page.get_by_label("Turma").select_option("5")
    page.get_by_role("button", name="Salvar").click()
'''


def test_klm_counts_operators_without_double_pointing():
    # click(M P BB) → fill no mesmo campo (H, K2) → Tab (K1) → fill sem apontar (K2)
    # → Enter (K1) → select(H, M PP BBBB) → click(M P BB)
    assert klm(ROTEIRO) == {
        "klm_k": 6, "klm_p": 4, "klm_b": 8, "klm_h": 2, "klm_m": 3,
        "klm_ms": 6 * 280 + 4 * 1100 + 8 * 100 + 2 * 400 + 3 * 1350,
        "campos": 3, "cliques": 2, "urls_digitadas": 0,
    }


@DOCKER
@pytest.mark.parametrize("tech", ["laravel", "go"])
def test_scaffolds_are_clean_for_sast(tech: str):
    assert sast(tech, ROOT / "scaffolds" / tech) == 0


@DOCKER
@pytest.mark.parametrize("lang", ["php", "go"])
def test_semgrep_rules_hit_bad_code_and_spare_good_code(lang: str, tmp_path: Path, capsys):
    tech = {"php": "laravel", "go": "go"}[lang]
    assert sast(tech, FIXTURES / "semgrep" / lang / "bom") == 0
    assert sast(tech, FIXTURES / "semgrep" / lang / "ruim") == 1
    saida = capsys.readouterr().out
    assert "PUCK_METRIC sast_sql_interpolado" in saida and "sast_erros_varredura 0" in saida


@DOCKER
def test_usability_replay_scores_and_verifies_tasks(tmp_path: Path):
    roteiros = tmp_path / "roteiros"
    shutil.copytree(FIXTURES / "usabilidade/referencia", roteiros)
    codigo, resultado = pontuar("referencia", ROOT / "oracle/referencia", roteiros)
    assert codigo == 0
    assert all(r["concluida"] for r in resultado.values())
    assert resultado["tarefa-1"]["telas"] == 3


@DOCKER
def test_usability_replay_rejects_unfinished_task(tmp_path: Path):
    roteiros = tmp_path / "roteiros"
    roteiros.mkdir()
    original = (FIXTURES / "usabilidade/referencia/tarefa-1.py").read_text()
    sem_salvar = original.replace('page.get_by_role("button", name="Salvar").click()\n', "")
    (roteiros / "tarefa-1.py").write_text(sem_salvar)
    codigo, resultado = pontuar("referencia", ROOT / "oracle/referencia", roteiros)
    assert codigo == 1 and not resultado["tarefa-1"]["concluida"]


@DOCKER
def test_dast_runs_against_reference():
    assert dast("referencia", ROOT / "oracle/referencia") in (0, 1)
