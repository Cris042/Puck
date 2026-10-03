import subprocess
from pathlib import Path

import pytest

from atena_benchmark.checks import CheckRunner
from atena_benchmark.config import ChecksConfig
from atena_benchmark.git_stats import collect_git_stats
from atena_benchmark.repo_tools import build_read_tools
from atena_benchmark.workspace import prepare_workspace


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


@pytest.fixture()
def source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.php").write_text("<?php\necho 1;\n")
    (repo / "old.php").write_text("<?php\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    (repo / "a.php").write_text("<?php\necho 2;\n")
    _git(repo, "commit", "-qam", "second")
    return repo


def test_workspace_accepts_sha_and_records_commit(source_repo: Path, tmp_path: Path):
    first = _git(source_repo, "rev-parse", "HEAD~1")
    ws = prepare_workspace(str(source_repo), first, tmp_path / "runs", "r1")
    assert ws.base_commit == first
    assert (ws.repo_dir / "a.php").read_text() == "<?php\necho 1;\n"
    assert _git(ws.repo_dir, "remote") == ""


def test_stats_and_diff_tool_include_new_files(source_repo: Path, tmp_path: Path):
    ws = prepare_workspace(str(source_repo), "main", tmp_path / "runs", "r2")
    (ws.repo_dir / "new.php").write_text("<?php\n// novo\n")
    (ws.repo_dir / "old.php").unlink()
    (ws.repo_dir / "a.php").write_text("<?php\necho 3;\n")

    stats = collect_git_stats(ws.repo_dir)
    assert stats["new_files"] == 1
    assert stats["deleted_files"] == 1
    assert stats["modified_files"] == 1
    assert stats["changed_files"] == 3

    tools = {t.name: t for t in build_read_tools(ws.repo_dir, CheckRunner(ws.repo_dir, ChecksConfig()))}
    assert "// novo" in tools["git_diff"].invoke({})


def test_list_files_skips_assets_and_vendor(tmp_path: Path):
    (tmp_path / "Lib" / "vendor").mkdir(parents=True)
    (tmp_path / "Lib" / "vendor" / "x.php").write_text("")
    (tmp_path / "font.svg").write_text("")
    (tmp_path / "app.php").write_text("")
    tools = {t.name: t for t in build_read_tools(tmp_path, CheckRunner(tmp_path, ChecksConfig()))}
    assert tools["list_files"].invoke({"pattern": "*"}) == "app.php"
