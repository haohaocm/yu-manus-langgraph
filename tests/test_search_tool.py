"""CE-6 阶段 C：semantic_search 工具单测。"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.prompts import NEXT_STEP_PROMPT
from app.tools.loader import load_agent_tools
from app.tools.search_tools import (
    clear_search_index_cache,
    semantic_search,
    semantic_search_text,
)


def _settings() -> Settings:
    get_settings.cache_clear()
    clear_search_index_cache()
    return Settings(
        workspace_root=".",
        search_mode="corpus",  # CE-6 回归：只扫 artifacts/corpus
        embedding_backend="http",
        hybrid_alpha=0.5,
        mcp_enabled=False,
    )


def test_c_t1_invoke_prints_scores() -> None:
    """C-T1: invoke 含 path= 与 score；打印打分。"""
    s = _settings()
    query = "简历如何写出量化成果和可验证结果"
    out = semantic_search_text(query, top_k=5, rebuild=True, settings=s)
    print(f"\n=== semantic_search tool output ===\n{out}\n")
    assert "path=" in out
    assert "score=" in out
    assert "job_resume_tips.md" in out or "job_journey_essay.md" in out


def test_c_t2_loader_includes_tool() -> None:
    """C-T2: load_agent_tools 含 semantic_search。"""
    names = {t.name for t in load_agent_tools(_settings(), persist_long_results=False)}
    assert "semantic_search" in names
    assert {"list_dir", "read_file", "grep", "terminate"} <= names


def test_c_t3_paths_in_workspace() -> None:
    """C-T3: 返回 path 无 ../ 逃逸。"""
    out = semantic_search_text("技术面试算法准备", top_k=5, rebuild=True, settings=_settings())
    assert "../" not in out
    assert "path=artifacts/corpus/" in out or "hits=0" in out


def test_c_t4_no_hits_friendly() -> None:
    """C-T4: 乱码 query → 友好 no hits / 低分结果，非 traceback。"""
    out = semantic_search_text("zzzzqwertyuiopasdfgh", top_k=3, rebuild=True, settings=_settings())
    assert "error:" not in out or "empty" not in out
    assert "Traceback" not in out
    assert "semantic_search" in out


def test_empty_query() -> None:
    out = semantic_search_text("  ", settings=_settings())
    assert out.startswith("semantic_search: error:")


def test_prompt_mentions_semantic_search() -> None:
    assert "semantic_search" in NEXT_STEP_PROMPT


def test_tool_decorator_invoke() -> None:
    clear_search_index_cache()
    # StructuredTool via @tool
    text = semantic_search.invoke(
        {"query": "Offer谈薪与签字费", "top_k": 3, "rebuild": True}
    )
    print(f"\n=== @tool invoke ===\n{text}\n")
    assert "score=" in text
