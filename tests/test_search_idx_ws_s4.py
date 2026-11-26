"""IDX-WS S4：semantic_search 文案 / 缓存键 / 提示词。"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.prompts import NEXT_STEP_PROMPT
from app.tools.search_tools import (
    _cache_key,
    clear_search_index_cache,
    semantic_search,
)


def test_s4_tool_docstring_mentions_workspace_not_path_arg() -> None:
    doc = (semantic_search.description or "") + (semantic_search.__doc__ or "")
    # LangChain StructuredTool 用 description
    text = getattr(semantic_search, "description", None) or doc
    assert "workspace" in text.lower() or "WORKSPACE" in text
    assert "corpus" in text.lower() or "SEARCH_MODE" in text
    assert "rebuild" in text.lower()


def test_s4_prompt_says_query_not_folder_path() -> None:
    assert "semantic_search" in NEXT_STEP_PROMPT
    assert "NOT a folder path" in NEXT_STEP_PROMPT or "not a folder path" in NEXT_STEP_PROMPT.lower()
    assert "WORKSPACE_ROOT" in NEXT_STEP_PROMPT


def test_s4_cache_key_includes_ignore_and_mode() -> None:
    get_settings.cache_clear()
    clear_search_index_cache()
    a = Settings(
        workspace_root=".",
        search_mode="workspace",
        search_ignore_dirs=".venv",
        search_globs="*.py",
        search_max_file_bytes=1000,
        search_max_chunks=100,
    )
    b = Settings(
        workspace_root=".",
        search_mode="corpus",
        search_ignore_dirs=".venv",
        search_globs="*.py",
        search_max_file_bytes=1000,
        search_max_chunks=100,
    )
    c = Settings(
        workspace_root=".",
        search_mode="workspace",
        search_ignore_dirs=".venv,node_modules",
        search_globs="*.py",
        search_max_file_bytes=1000,
        search_max_chunks=100,
    )
    assert _cache_key(a) != _cache_key(b)
    assert _cache_key(a) != _cache_key(c)
