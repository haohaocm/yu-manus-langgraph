"""IDX-WS S1：search scope 配置解析与 ignore / 上限。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.search.scope import (
    SearchScopeError,
    ensure_chunk_budget,
    ignore_dir_names,
    is_file_within_size_limit,
    normalize_search_mode,
    parse_csv_list,
    path_has_ignored_dir,
    search_glob_patterns,
    should_skip_directory,
)


def test_parse_csv_list_trims_and_skips_empty() -> None:
    assert parse_csv_list(" a, b ,,c ") == ("a", "b", "c")
    assert parse_csv_list("") == ()
    assert parse_csv_list(None) == ()


def test_normalize_search_mode_default_and_invalid() -> None:
    assert normalize_search_mode(Settings(search_mode="workspace")) == "workspace"
    assert normalize_search_mode(Settings(search_mode="CORPUS")) == "corpus"
    with pytest.raises(SearchScopeError, match="invalid search_mode"):
        normalize_search_mode(Settings(search_mode="all"))


def test_ignore_dir_names_contains_venv() -> None:
    names = ignore_dir_names(Settings())
    assert ".venv" in names
    assert "node_modules" in names
    assert ".git" in names


def test_path_has_ignored_dir_and_should_skip(tmp_path: Path) -> None:
    settings = Settings()
    nested = tmp_path / "src" / ".venv" / "lib"
    nested.mkdir(parents=True)
    assert path_has_ignored_dir(nested, ignore_dir_names(settings))
    assert should_skip_directory(tmp_path / ".venv", settings)
    assert not should_skip_directory(tmp_path / "src", settings)


def test_search_glob_patterns_default_includes_py() -> None:
    globs = search_glob_patterns(Settings())
    assert "*.py" in globs
    assert "*.md" in globs


def test_is_file_within_size_limit_skips_large(tmp_path: Path) -> None:
    small = tmp_path / "ok.py"
    small.write_bytes(b"x" * 100)
    big = tmp_path / "big.py"
    big.write_bytes(b"y" * 1000)
    settings = Settings(search_max_file_bytes=500)
    assert is_file_within_size_limit(small, settings) is True
    assert is_file_within_size_limit(big, settings) is False


def test_ensure_chunk_budget_raises_when_over() -> None:
    settings = Settings(search_max_chunks=10)
    ensure_chunk_budget(10, settings)  # equal OK
    with pytest.raises(SearchScopeError, match="search_max_chunks"):
        ensure_chunk_budget(11, settings)
