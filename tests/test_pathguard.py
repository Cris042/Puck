from pathlib import Path

import pytest

from atena_benchmark.pathguard import UnsafePathError, safe_repo_path


def test_safe_path_stays_inside_repo(tmp_path: Path):
    assert safe_repo_path(tmp_path, "src/file.php") == (tmp_path / "src/file.php").resolve()


def test_path_traversal_is_blocked(tmp_path: Path):
    with pytest.raises(UnsafePathError):
        safe_repo_path(tmp_path, "../secret.txt")


def test_git_directory_is_blocked(tmp_path: Path):
    with pytest.raises(UnsafePathError):
        safe_repo_path(tmp_path, ".git/config")
