"""Fase D: qualidade de código, com a régua do harness e a mesma leitura nas duas stacks."""

import os
import shutil
from pathlib import Path

import pytest

from atena_benchmark.qualidade import (
    _tipos_go,
    dependencias_diretas,
    medir,
    metricas_grafo,
    metricas_jscpd,
    metricas_lizard,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
DOCKER = pytest.mark.skipif(
    os.environ.get("PUCK_DOCKER_TESTS") != "1",
    reason="testes com Docker: PUCK_DOCKER_TESTS=1 (e `atena-bench sandbox build-images`)",
)


@pytest.mark.parametrize(("harness", "contrato"), [
    ("deptrac.yaml", "scaffolds/laravel/deptrac.yaml"),
    ("phpstan.neon", "scaffolds/laravel/phpstan.neon"),
    ("go-arch-lint.yml", "scaffolds/go/.go-arch-lint.yml"),
])
def test_harness_ruler_is_the_published_contract(harness: str, contrato: str):
    assert (ROOT / "oracle/qualidade" / harness).read_bytes() == (ROOT / contrato).read_bytes()


def test_module_graph_finds_cycles_and_blast_radius():
    arestas = {("a", "b"), ("b", "a"), ("c", "a"), ("d", "c")}
    metricas = metricas_grafo(arestas, {"a", "b", "c", "d"})
    assert metricas["ciclos_modulos"] == 1 and metricas["modulos_em_ciclo"] == 2
    # dependem de a: b, c, d (transitivo) → raio 3; de b: a, c, d → 3; de c: d → 1; de d: 0
    assert metricas["raio_impacto_max"] == 3
    assert metricas["raio_impacto_medio_x100"] == 175


def test_lizard_and_jscpd_parsing():
    linhas = "\n".join([
        '5,1,20,0,5,"f@1-5@a.go","a.go","f","f",1,5',
        '30,12,200,2,40,"g@10-49@a.go","a.go","g","g",10,49',
    ])
    metricas = metricas_lizard(linhas, "go")
    assert metricas["funcoes"] == 2 and metricas["cc_max"] == 12
    assert metricas["funcoes_cc_acima_10"] == 1 and metricas["funcoes_longas"] == 1
    assert metricas_jscpd({"statistics": {"total": {"clones": 2, "duplicatedLines": 30,
                                                    "percentage": 4.56}}}) == {
        "dup_blocos": 2, "dup_linhas": 30, "dup_permil": 46}


def test_go_type_counting_includes_type_blocks():
    fonte = "type A interface{ X() }\ntype B struct{}\ntype (\n\tC interface {\n\t}\n\tD int\n)\n"
    assert _tipos_go(fonte) == (2, 4)


def test_direct_dependencies_ignore_indirect_ones():
    assert dependencias_diretas("go", ROOT / "scaffolds/go") == 2
    assert dependencias_diretas("laravel", ROOT / "scaffolds/laravel") > 5


def _sobrepor(tmp_path: Path, tech: str, overlay: Path) -> Path:
    destino = tmp_path / tech
    shutil.copytree(ROOT / "scaffolds" / tech, destino)
    shutil.copytree(overlay, destino, dirs_exist_ok=True)
    return destino


@DOCKER
@pytest.mark.parametrize("tech", ["laravel", "go"])
def test_both_stacks_read_the_same_structure_the_same_way(tech: str, tmp_path: Path):
    esqueleto = medir(tech, ROOT / "scaffolds" / tech)
    amostra = medir(tech, _sobrepor(tmp_path, tech, FIXTURES / "qualidade" / tech))
    assert esqueleto["ciclos_modulos"] == 0 and esqueleto["arch_violacoes"] == 0
    assert amostra["ciclos_modulos"] == 1 and amostra["modulos_em_ciclo"] == 2
    assert amostra["arch_violacoes"] == 0, "actor → actor de outro módulo é permitido"
    assert amostra["dup_blocos"] == esqueleto["dup_blocos"] + 1
    assert amostra["cc_max"] == 7


@DOCKER
@pytest.mark.parametrize("tech", ["laravel", "go"])
def test_planted_layer_violations_are_counted_equally(tech: str, tmp_path: Path):
    quebrado = medir(tech, _sobrepor(tmp_path, tech, FIXTURES / "arquitetura" / tech))
    assert quebrado["arch_violacoes"] == 2
