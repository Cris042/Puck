from __future__ import annotations

import fnmatch
import json
import subprocess
from pathlib import Path

from langchain.tools import tool

from .checks import CheckRunner
from .git_stats import mark_untracked_as_intent_to_add
from .pathguard import safe_repo_path

MAX_READ_CHARS = 40_000
MAX_TOOL_OUTPUT = 30_000
MAX_LISTED_FILES = 1000
DEFAULT_EXCLUDED_DIRS = {".git", "vendor", "node_modules", ".idea", ".vscode"}
# Assets binários/estáticos: poluem listagens e buscas e não são alvo de refatoração.
DEFAULT_EXCLUDED_SUFFIXES = {
    ".svg", ".ttf", ".otf", ".woff", ".woff2", ".eot", ".png", ".jpg", ".jpeg", ".gif",
    ".ico", ".pdf", ".zip", ".map", ".dat",
}


def _iter_repo_files(repo: Path, pattern: str):
    for path in sorted(repo.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo)
        if any(part in DEFAULT_EXCLUDED_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() in DEFAULT_EXCLUDED_SUFFIXES:
            continue
        rel_s = rel.as_posix()
        if fnmatch.fnmatch(rel_s, pattern) or fnmatch.fnmatch(path.name, pattern):
            yield path, rel_s


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    return (completed.stdout + "\n" + completed.stderr).strip()[-MAX_TOOL_OUTPUT:]


def build_read_tools(repo: Path, checks: CheckRunner):
    @tool
    def list_files(pattern: str = "*") -> str:
        """Lista arquivos do repositório. Use glob simples como '*.php' ou 'Controller/*.php'.

        Dependências (vendor) e assets binários (fontes, imagens) são omitidos.
        """
        files = [rel_s for _, rel_s in _iter_repo_files(repo, pattern)]
        listed = "\n".join(files[:MAX_LISTED_FILES])
        if len(files) > MAX_LISTED_FILES:
            listed += f"\n... truncado: {len(files)} arquivos; refine o padrão."
        return listed or "Nenhum arquivo encontrado."

    @tool
    def read_file(path: str, start_line: int = 1, end_line: int = 400) -> str:
        """Lê um intervalo de linhas de um arquivo dentro do repositório."""
        target = safe_repo_path(repo, path)
        if not target.is_file():
            return f"Arquivo não encontrado: {path}"
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, start_line)
        end = max(start, end_line)
        selected = [f"{i}: {lines[i-1]}" for i in range(start, min(end, len(lines)) + 1)]
        text = "\n".join(selected)
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS] + "\n... truncado; leia um intervalo menor."
        elif end < len(lines):
            text += f"\n... arquivo tem {len(lines)} linhas."
        return text

    @tool
    def search_text(query: str, pattern: str = "*") -> str:
        """Busca texto literal nos arquivos do repositório e retorna até 200 ocorrências."""
        matches: list[str] = []
        for path, rel_s in _iter_repo_files(repo, pattern):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, start=1):
                if query in line:
                    matches.append(f"{rel_s}:{line_no}: {line.strip()}")
                    if len(matches) >= 200:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "Nenhuma ocorrência encontrada."

    @tool
    def git_diff() -> str:
        """Mostra o diff atual contra a linha de base do experimento, incluindo arquivos novos."""
        mark_untracked_as_intent_to_add(repo)
        return _git(repo, "diff", "HEAD", "--", ".") or "Nenhuma alteração."

    @tool
    def git_status() -> str:
        """Mostra arquivos modificados, criados e removidos no workspace."""
        return _git(repo, "status", "--short")

    @tool
    def run_check(name: str) -> str:
        """Executa um check permitido pelo benchmark. Use apenas nomes retornados pela configuração."""
        try:
            result = checks.run(name)
            return result.model_dump_json(indent=2)
        except KeyError as exc:
            return json.dumps({"error": str(exc), "available": checks.names()})

    return [list_files, read_file, search_text, git_diff, git_status, run_check]


def build_legacy_tools(legacy: Path):
    """Acesso somente-leitura ao sistema legado no SHA fixado (sem `.git`, sem histórico futuro).

    Contexto do legado idêntico em M1 e M2. Provisório: será substituído por
    `buscar_contexto_legado` (RAG congelado) na etapa 4 do protocolo.
    """

    @tool
    def legado_listar(pattern: str = "*") -> str:
        """Lista arquivos do sistema LEGADO (somente leitura). Glob simples, ex.: '*.php'."""
        files = [rel_s for _, rel_s in _iter_repo_files(legacy, pattern)]
        listed = "\n".join(files[:MAX_LISTED_FILES])
        if len(files) > MAX_LISTED_FILES:
            listed += f"\n... truncado: {len(files)} arquivos; refine o padrão."
        return listed or "Nenhum arquivo encontrado."

    @tool
    def legado_ler(path: str, start_line: int = 1, end_line: int = 400) -> str:
        """Lê um intervalo de linhas de um arquivo do sistema LEGADO (somente leitura)."""
        target = safe_repo_path(legacy, path)
        if not target.is_file():
            return f"Arquivo não encontrado no legado: {path}"
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, start_line)
        end = max(start, end_line)
        text = "\n".join(f"{i}: {lines[i-1]}" for i in range(start, min(end, len(lines)) + 1))
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS] + "\n... truncado; leia um intervalo menor."
        elif end < len(lines):
            text += f"\n... arquivo tem {len(lines)} linhas."
        return text

    @tool
    def legado_buscar(query: str, pattern: str = "*") -> str:
        """Busca texto literal no sistema LEGADO e retorna até 200 ocorrências com arquivo:linha."""
        matches: list[str] = []
        for path, rel_s in _iter_repo_files(legacy, pattern):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, start=1):
                if query in line:
                    matches.append(f"{rel_s}:{line_no}: {line.strip()}")
                    if len(matches) >= 200:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "Nenhuma ocorrência encontrada no legado."

    return [legado_listar, legado_ler, legado_buscar]


def build_write_tools(repo: Path, checks: CheckRunner):
    read_tools = build_read_tools(repo, checks)

    @tool
    def write_file(path: str, content: str) -> str:
        """Cria ou substitui um arquivo no workspace. Não permite escrita fora do repositório."""
        target = safe_repo_path(repo, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Arquivo gravado: {path} ({len(content)} caracteres)"

    @tool
    def replace_text(path: str, old: str, new: str, count: int = 1) -> str:
        """Substitui texto literal em um arquivo. Falha se o texto antigo não existir."""
        target = safe_repo_path(repo, path)
        if not target.is_file():
            return f"Arquivo não encontrado: {path}"
        content = target.read_text(encoding="utf-8", errors="replace")
        occurrences = content.count(old)
        if occurrences == 0:
            return "Texto antigo não encontrado; nenhuma alteração aplicada."
        updated = content.replace(old, new, count if count > 0 else occurrences)
        target.write_text(updated, encoding="utf-8")
        return f"Substituição aplicada em {path}; ocorrências encontradas: {occurrences}."

    @tool
    def delete_file(path: str) -> str:
        """Remove um arquivo do workspace quando a tarefa exigir explicitamente."""
        target = safe_repo_path(repo, path)
        if not target.is_file():
            return f"Arquivo não encontrado: {path}"
        target.unlink()
        return f"Arquivo removido: {path}"

    return [*read_tools, write_file, replace_text, delete_file]
