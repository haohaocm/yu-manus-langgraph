"""CE-6 阶段 D：提示词分工断言 + semantic_search → read_file → terminate 假模型图。"""

from langchain_core.messages import AIMessage

from app.config import Settings
from app.manus import run_manus
from app.prompts import NEXT_STEP_PROMPT
from app.tools.loader import load_agent_tools
from app.tools.search_tools import clear_search_index_cache
from tests.test_phase1_manus_graph import ScriptedChatModel


def _tools():
    clear_search_index_cache()
    return load_agent_tools(
        Settings(
            mcp_enabled=False,
            embedding_backend="http",
            hybrid_alpha=0.5,
            workspace_root=".",
            search_mode="corpus",
        )
    )


def test_d_t1_prompt_routing_keywords():
    """D-T1: prompt 含 semantic_search 与分工关键词。"""
    text = NEXT_STEP_PROMPT
    assert "semantic_search" in text
    assert "grep" in text
    assert "read_file" in text
    assert "list_dir" in text
    assert "Do not invent" in text or "never invent" in text.lower()
    # 决策意图信号
    assert "Exact symbol" in text or "exact" in text.lower()
    assert "Natural-language" in text or "topical" in text.lower()
    assert "rebuild" in text.lower()


def test_d_t2_graph_semantic_search_then_read_then_terminate():
    """D-T2: 假模型 semantic_search → read_file → terminate → summarize。"""
    tools = _tools()
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="search corpus for resume quantification tips",
                tool_calls=[
                    {
                        "name": "semantic_search",
                        "args": {
                            "query": "简历如何写出量化成果",
                            "top_k": 5,
                            "rebuild": True,
                        },
                        "id": "s1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="read the top hit for full text",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {
                            "path": "artifacts/corpus/job_resume_tips.md",
                            "offset": 1,
                            "limit": 40,
                        },
                        "id": "r1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="done",
                tool_calls=[
                    {
                        "name": "terminate",
                        "args": {
                            "outcome": "success",
                            "reason": "found resume quantification guidance",
                        },
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="简历应写成可验证结果，并用数字量化成果，例如延迟从 800ms 降到 200ms。"
            ),
        ]
    )
    out = run_manus(
        "语料里关于简历量化成果怎么写？先语义检索再读原文。",
        model=model,
        max_steps=8,
        tools=tools,
    )
    print("\n=== D-T2 run_manus ===")
    print("status=", out["status"])
    print("answer=", out["answer"])
    print("logs:\n", "\n".join(out["step_logs"]))

    assert out["status"] == "completed"
    logs = "\n".join(out["step_logs"])
    assert "semantic_search" in logs
    assert "read_file" in logs
    assert "terminate" in logs
    assert "summarize" in logs
    # 关键标识：量化 / 800ms / 可验证 等
    answer = out["answer"]
    assert any(k in answer for k in ("量化", "800", "可验证", "简历"))
