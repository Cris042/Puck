"""Qualidade de código por linguagem (protocolo 4.3), medida no esqueleto e no final (delta).

Referência conceitual: arch-fitness-review (Ca/Ce, instabilidade I = Ce/(Ca+Ce), abstratividade A,
distância D = |A+I−1|, ciclos, duplicação, raio de impacto). Implementação própria por linguagem.

As configurações de arquitetura e análise estática são as do HARNESS (`oracle/qualidade/`, cópias
do contrato dos esqueletos), aplicadas por cima das do projeto: o agente não muda a régua.

Comparáveis entre techs: complexidade (lizard), duplicação (jscpd), ciclos e raio de impacto entre
módulos, violações de fronteira, achados de análise estática. Só dentro da tech: LCOM (PHP),
abstratividade e distância (definições diferentes em PHP e Go).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

from .sandbox import ROOT, DependencyError, _env_args, deps_volume, print_metrics, tech_spec

QUALIDADE_IMAGE = "puck-qualidade"
# Fontes de produção analisadas (testes ficam fora de complexidade e duplicação).
FONTES = {"laravel": ("app", "routes", "database"), "go": ("cmd", "internal")}
LINGUAGEM_LIZARD = {"laravel": "php", "go": "go"}
# Object Calisthenics, regra 7 (base técnica 2.2): tamanho máximo de função.
LIMITE_LINHAS_FUNCAO = {"laravel": 20, "go": 30}
LIMITE_CCN = 10

SCRIPT_LARAVEL = """
cp -a /app/. /work/ && cd /work && cp -a /deps/vendor ./vendor && composer dump-autoload -q
cp /harness/deptrac.yaml deptrac.yaml && cp /harness/phpstan.neon phpstan.neon
php vendor/bin/deptrac analyse --no-progress --formatter=json --output=/out/deptrac.json >/dev/null 2>&1
php vendor/bin/phpstan analyse --no-progress --memory-limit=1G --error-format=json > /out/phpstan.json 2>/dev/null
php /opt/phpmetrics.phar --report-json=/out/phpmetrics.json app/ >/dev/null 2>&1
true
"""

SCRIPT_GO = """
cp -a /app/. /work/ && cd /work && cp /harness/go-arch-lint.yml .go-arch-lint.yml
go-arch-lint check --json > /out/arch.json 2>/dev/null
staticcheck -f json ./... > /out/staticcheck.json 2>/dev/null
go vet ./... 2> /out/vet.txt
go list -json ./... > /out/golist.json 2>/dev/null
true
"""


# ---------------------------------------------------------------- execução


def _etapa_linguagem(tech: str, repo: Path, saida: Path) -> None:
    spec = tech_spec(tech)
    deps = deps_volume(tech, repo)
    script = SCRIPT_LARAVEL if tech == "laravel" else SCRIPT_GO
    subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-w", "/work",
         "-v", f"{repo.resolve()}:/app:ro", "-v", f"{deps}:/deps",
         "-v", f"{ROOT / 'oracle' / 'qualidade'}:/harness:ro", "-v", f"{saida}:/out",
         *_env_args(spec.env), spec.image, "sh", "-c", script],
        capture_output=True, text=True, check=False, timeout=1800,
    )


def _etapa_comum(tech: str, repo: Path, saida: Path) -> None:
    fontes = [f"/src/{d}" for d in FONTES[tech] if (repo / d).is_dir()]
    if not fontes:
        return
    linguagem = LINGUAGEM_LIZARD[tech]
    excluir = "**/*_test.go" if tech == "go" else "**/vendor/**"
    script = (
        f"lizard -l {linguagem} --csv -x '*_test.go' {' '.join(fontes)} > /out/lizard.csv; "
        f"jscpd --silent --reporters json --output /out --format {linguagem} --min-tokens 50 "
        f"--ignore '{excluir}' {' '.join(fontes)} >/dev/null 2>&1; true"
    )
    subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{repo.resolve()}:/src:ro",
         "-v", f"{saida}:/out", QUALIDADE_IMAGE, "sh", "-c", script],
        capture_output=True, text=True, check=False, timeout=1800,
    )


# ---------------------------------------------------------------- métricas comuns


def metricas_lizard(texto_csv: str, tech: str) -> dict[str, int]:
    funcoes = []
    for linha in csv.reader(io.StringIO(texto_csv)):
        if len(linha) < 11:
            continue
        nloc, ccn = int(linha[0]), int(linha[1])
        inicio, fim = int(linha[9]), int(linha[10])
        funcoes.append((nloc, ccn, fim - inicio + 1))
    if not funcoes:
        return {"funcoes": 0}
    ccns = sorted(f[1] for f in funcoes)
    return {
        "funcoes": len(funcoes),
        "nloc": sum(f[0] for f in funcoes),
        "cc_media_x100": round(100 * statistics.fmean(ccns)),
        "cc_p90": ccns[min(len(ccns) - 1, int(0.9 * len(ccns)))],
        "cc_max": ccns[-1],
        "funcoes_cc_acima_10": sum(1 for c in ccns if c > LIMITE_CCN),
        "funcao_linhas_max": max(f[2] for f in funcoes),
        "funcoes_longas": sum(1 for f in funcoes if f[2] > LIMITE_LINHAS_FUNCAO[tech]),
    }


def metricas_jscpd(relatorio: dict) -> dict[str, int]:
    total = relatorio.get("statistics", {}).get("total", {})
    return {
        "dup_blocos": int(total.get("clones", 0)),
        "dup_linhas": int(total.get("duplicatedLines", 0)),
        "dup_permil": round(10 * float(total.get("percentage", 0))),
    }


# ---------------------------------------------------------------- grafo de módulos


def _componentes_fortes(grafo: dict[str, set[str]]) -> list[set[str]]:
    """Tarjan: componentes fortemente conexos."""
    indice, baixo, pilha, na_pilha, saida = {}, {}, [], set(), []
    contador = [0]

    def visitar(v: str) -> None:
        indice[v] = baixo[v] = contador[0]
        contador[0] += 1
        pilha.append(v)
        na_pilha.add(v)
        for w in grafo.get(v, ()):
            if w not in indice:
                visitar(w)
                baixo[v] = min(baixo[v], baixo[w])
            elif w in na_pilha:
                baixo[v] = min(baixo[v], indice[w])
        if baixo[v] == indice[v]:
            componente = set()
            while True:
                w = pilha.pop()
                na_pilha.discard(w)
                componente.add(w)
                if w == v:
                    break
            saida.append(componente)

    for v in sorted(grafo):
        if v not in indice:
            visitar(v)
    return saida


def metricas_grafo(arestas: set[tuple[str, str]], modulos: set[str]) -> dict[str, int]:
    """Ciclos entre módulos e raio de impacto (quantos módulos dependem, transitivamente, de cada um)."""
    grafo: dict[str, set[str]] = {m: set() for m in modulos}
    reverso: dict[str, set[str]] = {m: set() for m in modulos}
    for origem, destino in arestas:
        if origem != destino:
            grafo[origem].add(destino)
            reverso[destino].add(origem)
    ciclos = [c for c in _componentes_fortes(grafo) if len(c) > 1]
    raios = []
    for m in modulos:
        vistos, fila = set(), [m]
        while fila:
            atual = fila.pop()
            for dependente in reverso[atual]:
                if dependente not in vistos and dependente != m:
                    vistos.add(dependente)
                    fila.append(dependente)
        raios.append(len(vistos))
    return {
        "modulos": len(modulos),
        "dependencias_entre_modulos": sum(len(v) for v in grafo.values()),
        "ciclos_modulos": len(ciclos),
        "modulos_em_ciclo": sum(len(c) for c in ciclos),
        "raio_impacto_max": max(raios, default=0),
        "raio_impacto_medio_x100": round(100 * statistics.fmean(raios)) if raios else 0,
    }


def _medias_martin(pacotes: list[tuple[float, float]]) -> dict[str, int]:
    """(abstratividade, instabilidade) por pacote → médias de A, I e D = |A + I − 1| (×1000)."""
    if not pacotes:
        return {}
    return {
        "abstracao_media_x1000": round(1000 * statistics.fmean(a for a, _ in pacotes)),
        "instabilidade_media_x1000": round(1000 * statistics.fmean(i for _, i in pacotes)),
        "distancia_media_x1000": round(1000 * statistics.fmean(abs(a + i - 1) for a, i in pacotes)),
    }


# ---------------------------------------------------------------- PHP


def _modulo_php(classe: str) -> str | None:
    partes = classe.split("\\")
    if len(partes) > 2 and partes[0] == "App" and partes[1] == "Modulos":
        return partes[2]
    if len(partes) > 1 and partes[0] == "App" and partes[1] in ("Infra", "Comum"):
        return partes[1]
    return None


def metricas_php(phpmetrics: dict, deptrac: dict, phpstan: dict) -> dict[str, int]:
    metricas: dict[str, int] = {}
    classes = [v for v in phpmetrics.values() if isinstance(v, dict)
               and v.get("_type") in ("Hal\\Metric\\ClassMetric", "Hal\\Metric\\InterfaceMetric")]
    arestas, modulos = set(), set()
    for classe in classes:
        origem = _modulo_php(classe["name"])
        if origem is None:
            continue
        modulos.add(origem)
        for dependencia in classe.get("externals", []):
            destino = _modulo_php(dependencia)
            if destino is not None:
                modulos.add(destino)
                arestas.add((origem, destino))
    metricas |= metricas_grafo(arestas, modulos)

    pacotes = [(float(v.get("abstraction", 0)), float(v.get("instability", 0)))
               for v in phpmetrics.values() if isinstance(v, dict)
               and v.get("_type") == "Hal\\Metric\\PackageMetric"
               and v.get("name", "").startswith(("App\\Modulos\\", "App\\Infra\\"))
               and "instability" in v]
    metricas |= _medias_martin(pacotes)
    lcoms = [c["lcom"] for c in classes if "lcom" in c and _modulo_php(c["name"])]
    if lcoms:
        metricas["lcom_media_x100"] = round(100 * statistics.fmean(lcoms))
    if deptrac:
        metricas["arch_violacoes"] = int(deptrac.get("Report", {}).get("Violations", 0))
    if phpstan:
        totais = phpstan.get("totals", {})
        metricas["estatica_erros"] = int(totais.get("errors", 0)) + int(totais.get("file_errors", 0))
    return metricas


# ---------------------------------------------------------------- Go

_TIPO = re.compile(r"^type\s+(\w+)(\[[^\]]*\])?\s+(\S+)")
_TIPO_BLOCO = re.compile(r"^\s+(\w+)(\[[^\]]*\])?\s+(\S+)")


def _tipos_go(fonte: str) -> tuple[int, int]:
    """(interfaces, tipos) declarados num arquivo Go, incluindo blocos `type ( ... )`."""
    interfaces = tipos = 0
    no_bloco = False
    for linha in fonte.splitlines():
        if no_bloco:
            if linha.strip() == ")":
                no_bloco = False
                continue
            achado = _TIPO_BLOCO.match(linha)
        elif linha.startswith("type ("):
            no_bloco = True
            continue
        else:
            achado = _TIPO.match(linha)
        if achado:
            tipos += 1
            interfaces += achado.group(3).startswith("interface")
    return interfaces, tipos


def _decodificar_stream(texto: str) -> list[dict]:
    decoder, posicao, objetos = json.JSONDecoder(), 0, []
    texto = texto.strip()
    while posicao < len(texto):
        objeto, posicao = decoder.raw_decode(texto, posicao)
        objetos.append(objeto)
        while posicao < len(texto) and texto[posicao].isspace():
            posicao += 1
    return objetos


def metricas_go(repo: Path, golist: str, arch: dict, staticcheck: str, vet: str) -> dict[str, int]:
    pacotes = _decodificar_stream(golist) if golist.strip() else []
    if not pacotes:
        return {}
    modulo_go = pacotes[0].get("Module", {}).get("Path", "")
    prefixo = f"{modulo_go}/internal/"
    internos = {p["ImportPath"]: p for p in pacotes if p["ImportPath"].startswith(prefixo)}

    def modulo(caminho: str) -> str:
        return caminho[len(prefixo):].split("/")[0]

    arestas, modulos = set(), set()
    eferente = {c: set() for c in internos}
    aferente = {c: set() for c in internos}
    for caminho, pacote in internos.items():
        modulos.add(modulo(caminho))
        for importado in pacote.get("Imports", []):
            if importado in internos:
                eferente[caminho].add(importado)
                aferente[importado].add(caminho)
                arestas.add((modulo(caminho), modulo(importado)))
    metricas = metricas_grafo(arestas, modulos)

    martin = []
    for caminho, pacote in internos.items():
        ce, ca = len(eferente[caminho]), len(aferente[caminho])
        if ca + ce == 0:
            continue
        interfaces = tipos = 0
        for arquivo in pacote.get("GoFiles", []):
            rel = Path(pacote["Dir"]).relative_to("/work") / arquivo
            i, t = _tipos_go((repo / rel).read_text(encoding="utf-8", errors="replace"))
            interfaces, tipos = interfaces + i, tipos + t
        martin.append((interfaces / tipos if tipos else 0.0, ce / (ca + ce)))
    metricas |= _medias_martin(martin)

    if arch:
        payload = arch.get("Payload", {})
        metricas["arch_violacoes"] = sum(
            len(payload.get(k) or []) for k in ("ArchWarningsDeps", "ArchWarningsNotMatched",
                                                 "ArchWarningsDeepScan")
        )
    achados_staticcheck = _decodificar_stream(staticcheck) if staticcheck.strip() else []
    achados_vet = [linha for linha in vet.splitlines() if re.match(r"^\S+\.go:\d+:\d+: ", linha)]
    metricas["estatica_erros"] = len(achados_staticcheck) + len(achados_vet)
    return metricas


# ---------------------------------------------------------------- dependências declaradas


def dependencias_diretas(tech: str, repo: Path) -> int:
    if tech == "laravel":
        composer = repo / "composer.json"
        if not composer.is_file():
            return 0
        dados = json.loads(composer.read_text(encoding="utf-8"))
        return sum(1 for nome in {**dados.get("require", {}), **dados.get("require-dev", {})}
                   if "/" in nome)
    gomod = repo / "go.mod"
    if not gomod.is_file():
        return 0
    texto = gomod.read_text(encoding="utf-8")
    blocos = re.findall(r"require\s*\((.*?)\)", texto, re.S) + re.findall(r"^require\s+(\S+ \S+)", texto, re.M)
    return sum(1 for bloco in blocos for linha in bloco.splitlines()
               if linha.strip() and "// indirect" not in linha)


# ---------------------------------------------------------------- comando


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="replace") if caminho.is_file() else ""


def _json(caminho: Path) -> dict:
    texto = _ler(caminho).strip()
    try:
        return json.loads(texto) if texto else {}
    except json.JSONDecodeError:
        return {}


def medir(tech: str, repo: Path) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="puck-qualidade-") as tmp:
        saida = Path(tmp)
        os.chmod(saida, 0o777)
        _etapa_linguagem(tech, repo, saida)
        _etapa_comum(tech, repo, saida)
        metricas = metricas_lizard(_ler(saida / "lizard.csv"), tech)
        metricas |= metricas_jscpd(_json(saida / "jscpd-report.json"))
        if tech == "laravel":
            metricas |= metricas_php(_json(saida / "phpmetrics.json"), _json(saida / "deptrac.json"),
                                     _json(saida / "phpstan.json"))
        else:
            metricas |= metricas_go(repo, _ler(saida / "golist.json"), _json(saida / "arch.json"),
                                    _ler(saida / "staticcheck.json"), _ler(saida / "vet.txt"))
    metricas["deps_diretas"] = dependencias_diretas(tech, repo)
    return metricas


def qualidade(tech: str, repo: Path) -> int:
    try:
        metricas = medir(tech, repo)
    except DependencyError as exc:
        print(f"Dependências do projeto não resolveram:\n{exc}")
        return 2
    print_metrics(metricas)
    return 0

