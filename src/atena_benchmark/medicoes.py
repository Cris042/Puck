"""Medições do oráculo além da caracterização: SAST, DAST, dependências e carga (protocolo 4.5–4.6).

Todas rodam no sandbox, fora do alcance dos agentes, e imprimem `PUCK_METRIC <nome> <inteiro>`
(parser `puck_metrics`). Exit 0 = nenhum achado bloqueante; a contagem é a medida, não o exit.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from .sandbox import (
    ROOT,
    AppStartError,
    DependencyError,
    _env_args,
    app_running,
    deps_volume,
    print_metrics,
    run_tool,
    tech_spec,
)

SEMGREP_IMAGE = "semgrep/semgrep:1.179.0"
ZAP_IMAGE = "zaproxy/zap-stable:2.17.0"
K6_IMAGE = "grafana/k6:2.3.0"
LINGUAGEM = {"laravel": "php", "go": "go", "referencia": "python"}
SAST_EXCLUIDOS = ("vendor", "node_modules", "storage", "bootstrap/cache", "build")
RISCO_ZAP = {"3": "alto", "2": "medio", "1": "baixo", "0": "info"}


def _rodar(args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)


# ---------------------------------------------------------------- SAST


def contar_semgrep(saida_json: str) -> dict[str, int]:
    dados = json.loads(saida_json)
    contagem = Counter(r["check_id"].rsplit(".", 1)[-1] for r in dados.get("results", []))
    metricas = {f"sast_{regra.replace('-', '_')}": n for regra, n in contagem.items()}
    metricas["sast_total"] = sum(contagem.values())
    metricas["sast_erros_varredura"] = len(dados.get("errors", []))
    return metricas


def sast(tech: str, repo: Path) -> int:
    linguagem = LINGUAGEM[tech]
    excluir = [arg for pasta in SAST_EXCLUIDOS for arg in ("--exclude", pasta)]
    completed = _rodar([
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{repo.resolve()}:/src:ro", "-v", f"{ROOT / 'config' / 'semgrep'}:/rules:ro",
        SEMGREP_IMAGE, "semgrep", "scan", "--metrics=off", "--disable-version-check",
        "--config", f"/rules/{linguagem}.yml", "--json", "--quiet", *excluir, "/src",
    ])
    try:
        metricas = contar_semgrep(completed.stdout)
    except json.JSONDecodeError:
        print(completed.stderr[-4000:])
        return 1
    print_metrics(metricas)
    return 0 if metricas["sast_total"] == 0 else 1


# ---------------------------------------------------------------- dependências


def contar_composer_audit(saida_json: str) -> dict[str, int]:
    dados = json.loads(saida_json or "{}")
    avisos = dados.get("advisories") or {}
    total = sum(len(v) for v in (avisos.values() if isinstance(avisos, dict) else []))
    return {"deps_vulnerabilidades": total, "deps_alcancaveis": total}


def contar_govulncheck(saida_json: str) -> dict[str, int]:
    """Stream de objetos JSON; vulnerabilidade alcançável = finding com função no trace."""
    decoder = json.JSONDecoder()
    posicao, todas, alcancaveis = 0, set(), set()
    texto = saida_json.strip()
    while posicao < len(texto):
        objeto, fim = decoder.raw_decode(texto, posicao)
        posicao = fim
        while posicao < len(texto) and texto[posicao].isspace():
            posicao += 1
        achado = objeto.get("finding")
        if not achado:
            continue
        todas.add(achado["osv"])
        trace = achado.get("trace") or []
        if trace and trace[0].get("function"):
            alcancaveis.add(achado["osv"])
    return {"deps_vulnerabilidades": len(todas), "deps_alcancaveis": len(alcancaveis)}


def auditoria(tech: str, repo: Path) -> int:
    """Com rede (base de vulnerabilidades), mas sem executar código do projeto."""
    spec = tech_spec(tech)
    if tech == "laravel":
        script = "cp -a /app/. /work/ && cd /work && composer audit --locked --format=json"
        volumes, env = [], spec.env
        contar = contar_composer_audit
    else:
        try:
            volumes = ["-v", f"{deps_volume(tech, repo)}:/deps"]
        except DependencyError as exc:
            print(f"Dependências do projeto não resolveram:\n{exc}")
            return 2
        script = "cp -a /app/. /work/ && cd /work && govulncheck -format json ./..."
        env = spec.env | {"GOPROXY": "https://proxy.golang.org"}
        contar = contar_govulncheck
    completed = _rodar(["docker", "run", "--rm", "-w", "/work", "-v", f"{repo.resolve()}:/app:ro",
                        *volumes, *_env_args(env), spec.image, "sh", "-c", script])
    try:
        metricas = contar(completed.stdout)
    except (json.JSONDecodeError, KeyError):
        print((completed.stdout + completed.stderr)[-4000:])
        return 1
    print_metrics(metricas)
    return 0 if metricas["deps_alcancaveis"] == 0 else 1


# ---------------------------------------------------------------- DAST


def contar_zap(relatorio: dict) -> dict[str, int]:
    contagem = Counter()
    for site in relatorio.get("site", []):
        for alerta in site.get("alerts", []):
            contagem[RISCO_ZAP.get(str(alerta.get("riskcode")), "info")] += 1
    return {f"dast_{nivel}": contagem.get(nivel, 0) for nivel in RISCO_ZAP.values()}


def dast(tech: str, repo: Path) -> int:
    """ZAP baseline (passivo + spider de 1 min) contra a aplicação na rede interna."""
    try:
        with app_running(tech, repo) as (current, url), tempfile.TemporaryDirectory() as saida:
            os.chmod(saida, 0o777)
            completed = run_tool(
                current, url, ZAP_IMAGE,
                ["zap-baseline.py", "-t", url, "-J", "zap.json", "-I", "-m", "1"],
                mounts=[f"{saida}:/zap/wrk:rw"], timeout=1200,
            )
            relatorio = Path(saida) / "zap.json"
            if not relatorio.is_file():
                print((completed.stdout + completed.stderr)[-4000:])
                return 1
            metricas = contar_zap(json.loads(relatorio.read_text(encoding="utf-8")))
    except DependencyError as exc:
        print(f"Dependências do projeto não resolveram:\n{exc}")
        return 2
    except AppStartError as exc:
        print(f"Aplicação não subiu:\n{exc}")
        return 3
    print_metrics(metricas)
    return 0 if metricas["dast_alto"] + metricas["dast_medio"] == 0 else 1


# ---------------------------------------------------------------- carga


def _metricas_k6(saida: str) -> dict[str, int]:
    metricas = {}
    for linha in saida.splitlines():
        partes = linha.strip().split()
        if len(partes) == 3 and partes[0] == "PUCK_METRIC":
            metricas[partes[1]] = int(partes[2])
    return metricas


def carga(tech: str, repo: Path, rodadas: int = 3, duracao: str = "30s") -> int:
    """Aquecimento + `rodadas` medições na MESMA instância; reporta a mediana e cada rodada."""
    mounts = [f"{ROOT / 'oracle' / 'carga'}:/carga:ro"]
    comando = ["run", "--quiet", "/carga/cenario.js"]
    try:
        with app_running(tech, repo) as (current, url):
            run_tool(current, url, K6_IMAGE, comando, {"DURACAO": "10s"}, mounts)  # aquecimento
            por_rodada = []
            for _ in range(rodadas):
                completed = run_tool(current, url, K6_IMAGE, comando, {"DURACAO": duracao}, mounts)
                metricas = _metricas_k6(completed.stdout)
                if not metricas:
                    print((completed.stdout + completed.stderr)[-4000:])
                    return 1
                por_rodada.append(metricas)
    except DependencyError as exc:
        print(f"Dependências do projeto não resolveram:\n{exc}")
        return 2
    except AppStartError as exc:
        print(f"Aplicação não subiu:\n{exc}")
        return 3
    final = {}
    for nome in sorted(por_rodada[0]):
        valores = [r.get(nome, 0) for r in por_rodada]
        final[nome] = round(statistics.median(valores))
        for i, valor in enumerate(valores, start=1):
            final[f"{nome}_r{i}"] = valor
    print_metrics(final)
    falhas = final.get("carga_leitura_falhas_permil", 0) + final.get("carga_escrita_falhas_permil", 0)
    return 0 if falhas == 0 else 1
