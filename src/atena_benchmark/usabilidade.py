"""Usabilidade por KLM/GOMS (protocolo 4.4) a partir de roteiros gravados com Playwright.

A UI é livre por desenho; então cada célula tem a SUA gravação de cada tarefa, feita por um
avaliador com `npx playwright@1.63.0 codegen --target python` contra a aplicação semeada
(`atena-bench sandbox subir`). O harness:

1. calcula o KLM das ações gravadas (análise estática do roteiro);
2. reexecuta o roteiro no sandbox, numa aplicação nova com o mesmo cenário, e confirma pela API
   que a tarefa foi concluída e quantas telas foram navegadas.

Tempos dos operadores: Card, Moran & Newell (1983); K para digitador médio não profissional.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .sandbox import ROOT, AppStartError, DependencyError, app_running, print_metrics, run_tool

USABILIDADE_IMAGE = "puck-usabilidade"
SOCAT_IMAGE = "alpine/socat:1.8.1.3"
TEMPOS_MS = {"K": 280, "P": 1100, "B": 100, "H": 400, "M": 1350}
CLIQUES = {"click", "check", "uncheck", "set_checked", "tap"}
DIGITACAO = {"fill", "type", "press_sequentially"}
CENARIO_BOOTSTRAP = {"NOME": "Secretaria Usabilidade", "EMAIL": "secretaria@escola.test",
                     "MATRICULA": "S0001", "SENHA": "Usabilidade#2026"}


def _acoes(codigo: str) -> list[tuple[str, str, list]]:
    """(método, alvo, argumentos literais) de cada ação, na ordem do roteiro."""
    acoes = []
    for no in ast.walk(ast.parse(codigo)):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
            argumentos = [a.value for a in no.args if isinstance(a, ast.Constant)]
            acoes.append((no.lineno, no.col_offset, no.func.attr, ast.unparse(no.func.value), argumentos))
    return [(nome, alvo, args) for _, _, nome, alvo, args in sorted(acoes)]


def klm(codigo: str) -> dict[str, int]:
    """Operadores K, P, B, H, M e tempo estimado (ms) das ações de usuário do roteiro.

    O codegen grava "clicar no campo" e "preencher" como duas ações; o preenchimento só cobra
    apontar (P, BB) quando o campo não acabou de receber o clique nem o foco por Tab.
    """
    ops = dict.fromkeys(TEMPOS_MS, 0)
    dispositivo = "mouse"
    campos = cliques = urls_digitadas = 0
    primeiro_goto = True
    anterior: tuple[str, str] = ("", "")

    def usar(alvo: str) -> None:
        nonlocal dispositivo
        if dispositivo != alvo:
            ops["H"] += 1
            dispositivo = alvo

    for nome, alvo, args in _acoes(codigo):
        if nome == "goto":
            if primeiro_goto:
                primeiro_goto = False
                continue
            urls_digitadas += 1
            usar("teclado")
            ops["M"] += 1
            ops["K"] += len(str(args[0]) if args else "") + 1
        elif nome in CLIQUES or nome == "dblclick":
            usar("mouse")
            ops["M"] += 1
            ops["P"] += 1
            ops["B"] += 4 if nome == "dblclick" else 2
            cliques += 1
        elif nome in ("select_option", "set_input_files"):
            usar("mouse")
            ops["M"] += 1
            ops["P"] += 2 if nome == "select_option" else 1
            ops["B"] += 4 if nome == "select_option" else 2
            campos += 1
        elif nome in DIGITACAO:
            focado = anterior == ("click", alvo) or anterior[0] == "press_tab"
            if not focado:
                usar("mouse")
                ops["M"] += 1
                ops["P"] += 1
                ops["B"] += 2
            usar("teclado")
            ops["K"] += len(str(args[0])) if args else 0
            campos += 1
        elif nome == "press":
            if anterior[0] not in DIGITACAO and anterior[0] != "press_tab":
                ops["M"] += 1
            usar("teclado")
            tecla = str(args[0]) if args else ""
            ops["K"] += len(tecla.split("+")) if tecla else 1
            if tecla == "Tab":
                anterior = ("press_tab", alvo)
                continue
        else:
            continue
        anterior = (nome, alvo)
    tempo = sum(ops[op] * TEMPOS_MS[op] for op in ops)
    return {**{f"klm_{op.lower()}": n for op, n in ops.items()}, "klm_ms": tempo,
            "campos": campos, "cliques": cliques, "urls_digitadas": urls_digitadas}


def pontuar(tech: str, repo: Path, roteiros: Path) -> tuple[int, dict]:
    """Reexecuta os roteiros no sandbox e combina conclusão, telas e KLM. Grava `usabilidade.json`."""
    scripts = sorted(roteiros.glob("tarefa-*.py"))
    if not scripts:
        print(f"Nenhum roteiro tarefa-*.py em {roteiros}")
        return 1, {}
    with tempfile.TemporaryDirectory() as saida:
        os.chmod(saida, 0o777)
        try:
            with app_running(tech, repo, bootstrap=CENARIO_BOOTSTRAP) as (current, url):
                completed = run_tool(
                    current, url, USABILIDADE_IMAGE,
                    ["python", "/usabilidade/executar.py", "/roteiros", "/saida/resultado.json"],
                    mounts=[f"{ROOT / 'oracle' / 'usabilidade'}:/usabilidade:ro",
                            f"{roteiros.resolve()}:/roteiros:ro", f"{saida}:/saida:rw"],
                    timeout=1800,
                )
        except DependencyError as exc:
            print(f"Dependências do projeto não resolveram:\n{exc}")
            return 2, {}
        except AppStartError as exc:
            print(f"Aplicação não subiu:\n{exc}")
            return 3, {}
        arquivo = Path(saida) / "resultado.json"
        if not arquivo.is_file():
            print((completed.stdout + completed.stderr)[-4000:])
            return 1, {}
        reexecucao = json.loads(arquivo.read_text(encoding="utf-8"))

    resultado, metricas = {}, {}
    for script in scripts:
        tarefa = script.stem
        dados = {**klm(script.read_text(encoding="utf-8")), **reexecucao.get(tarefa, {})}
        resultado[tarefa] = dados
        prefixo = f"usab_{tarefa.replace('-', '_')}"
        metricas[f"{prefixo}_concluida"] = int(bool(dados.get("concluida")))
        for chave in ("klm_ms", "klm_k", "klm_p", "klm_b", "klm_h", "klm_m", "campos", "cliques",
                      "telas", "navegacoes"):
            metricas[f"{prefixo}_{chave}"] = int(dados.get(chave, 0))
    (roteiros / "usabilidade.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print_metrics(metricas)
    return (0 if all(v["concluida"] for v in resultado.values()) else 1), resultado


def subir(tech: str, repo: Path, porta: int = 8080) -> int:
    """Aplicação semeada com o cenário, publicada em 127.0.0.1:<porta> para a gravação."""
    try:
        with app_running(tech, repo, bootstrap=CENARIO_BOOTSTRAP) as (current, url):
            semeado = run_tool(current, url, USABILIDADE_IMAGE,
                               ["python", "/usabilidade/executar.py", "--so-semear"],
                               mounts=[f"{ROOT / 'oracle' / 'usabilidade'}:/usabilidade:ro"])
            if semeado.returncode != 0:
                print((semeado.stdout + semeado.stderr)[-4000:])
                return 1
            ponte = f"{current.name}-ponte"
            current.containers.append(ponte)
            subprocess.run(["docker", "run", "-d", "--name", ponte, "-p", f"127.0.0.1:{porta}:8080",
                            SOCAT_IMAGE, "tcp-listen:8080,fork,reuseaddr",
                            f"tcp-connect:{current.app_host}:8080"], check=True, capture_output=True)
            subprocess.run(["docker", "network", "connect", current.network, ponte],
                           check=True, capture_output=True)
            print(f"Aplicação em http://127.0.0.1:{porta} com o cenário de usabilidade.")
            print(f"Grave cada tarefa com: npx playwright@1.63.0 codegen --target python "
                  f"-o tarefa-N.py http://127.0.0.1:{porta}")
            print("Ctrl+C encerra.")
            try:
                while True:
                    subprocess.run(["sleep", "3600"], check=False)
            except KeyboardInterrupt:
                return 0
    except DependencyError as exc:
        print(f"Dependências do projeto não resolveram:\n{exc}")
        return 2
    except AppStartError as exc:
        print(f"Aplicação não subiu:\n{exc}")
        return 3
