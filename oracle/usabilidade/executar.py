"""Reexecuta os roteiros gravados (`playwright codegen --target python`) contra a aplicação.

Uso no container (rede interna da aplicação, TARGET_URL definido):
  python executar.py --so-semear                 # só cria o cenário (sessão de gravação)
  python executar.py /roteiros /saida/resultado.json

Para cada `tarefa-N.py`: troca a origem gravada pela TARGET_URL, força headless, conta as
navegações da aba principal (telas) e verifica pela API se a tarefa foi concluída.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse

import cenario
from playwright.sync_api import BrowserContext

BASE = os.environ["TARGET_URL"].rstrip("/")
_ORIGEM = re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d+)?")


def preparar(codigo: str) -> str:
    codigo = _ORIGEM.sub(BASE, codigo)
    return codigo.replace("headless=False", "headless=True")


def executar_roteiro(caminho: Path) -> dict:
    navegacoes: list[str] = []
    original_new_page = BrowserContext.new_page
    paginas = []

    def new_page(self, *args, **kwargs):
        pagina = original_new_page(self, *args, **kwargs)
        paginas.append(pagina)
        pagina.on("framenavigated",
                  lambda frame: navegacoes.append(frame.url) if frame == pagina.main_frame else None)
        return pagina

    BrowserContext.new_page = new_page
    erro, texto_final = "", ""
    try:
        codigo = preparar(caminho.read_text(encoding="utf-8"))
        # Os roteiros do codegen fecham o navegador no fim: captura o texto antes do close.
        original_close = BrowserContext.close

        def close(self, *args, **kwargs):
            nonlocal texto_final
            if paginas and not paginas[-1].is_closed():
                texto_final = paginas[-1].inner_text("body")
            return original_close(self, *args, **kwargs)

        BrowserContext.close = close
        try:
            exec(compile(codigo, str(caminho), "exec"), {"__name__": "__main__"})
        finally:
            BrowserContext.close = original_close
    except Exception:  # o roteiro não completou: registrado, não derruba os demais
        erro = traceback.format_exc()[-2000:]
    finally:
        BrowserContext.new_page = original_new_page
    caminhos = [urlparse(url).path or "/" for url in navegacoes]
    return {"navegacoes": len(navegacoes), "telas": len(set(caminhos)), "caminhos": caminhos,
            "erro": erro, "texto_final": texto_final}


def main() -> int:
    if "--so-semear" in sys.argv:
        print(json.dumps(cenario.semear(BASE)))
        return 0
    roteiros, saida = Path(sys.argv[1]), Path(sys.argv[2])
    ids = cenario.semear(BASE)
    resultado = {}
    for roteiro in sorted(roteiros.glob("tarefa-*.py")):
        execucao = executar_roteiro(roteiro)
        execucao["concluida"] = not execucao["erro"] and cenario.verificar(
            BASE, ids, roteiro.stem, execucao["texto_final"])
        execucao.pop("texto_final")
        resultado[roteiro.stem] = execucao
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: {"concluida": v["concluida"], "telas": v["telas"]} for k, v in resultado.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
