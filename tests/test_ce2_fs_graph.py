"""CE-2.7：假模型串联 list_dir/grep/read_file + terminate + summarize。"""

from langchain_core.messages import AIMessage

from app.config import Settings
from app.manus import run_manus
from app.prompts import NEXT_STEP_PROMPT
from app.tools.loader import load_agent_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


def _fs_tools():
    return load_agent_tools(Settings(mcp_enabled=False))


def test_next_step_prompt_mentions_fs_discovery():
    assert "list_dir" in NEXT_STEP_PROMPT
    assert "grep" in NEXT_STEP_PROMPT
    assert "read_file" in NEXT_STEP_PROMPT
    assert "workspace root" in NEXT_STEP_PROMPT.lower() or "workspace" in NEXT_STEP_PROMPT.lower()


def test_loader_has_fs_tools():
    names = {t.name for t in _fs_tools()}
    assert {"list_dir", "read_file", "grep", "terminate"} <= names


def test_graph_grep_then_read_then_terminate():
    tools = _fs_tools()
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="search PathSandboxError",
                tool_calls=[
                    {
                        "name": "grep",
                        "args": {
                            "pattern": "PathSandboxError",
                            "path": "app",
                            "glob": "*.py",
                        },
                        "id": "g1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="read the sandbox module",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {
                            "path": "app/tools/path_sandbox.py",
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
                            "reason": "found PathSandboxError definition",
                        },
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="在 path_sandbox.py 中定义了 PathSandboxError，用于路径越界时抛出。"
            ),
        ]
    )
    out = run_manus(
        "PathSandboxError 定义在哪个文件？请先搜索再阅读。",
        model=model,
        max_steps=6,
        tools=tools,
    )
    assert out["status"] == "completed"
    logs = "\n".join(out["step_logs"])
    assert "grep" in logs
    assert "read_file" in logs
    assert "terminate" in logs
    assert "summarize" in logs
    assert "PathSandboxError" in out["answer"]


def test_graph_list_dir_then_read_then_terminate():
    tools = _fs_tools()
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="list tests",
                tool_calls=[
                    {
                        "name": "list_dir",
                        "args": {"path": "tests"},
                        "id": "l1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="read fs tools test",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {
                            "path": "tests/test_fs_tools.py",
                            "offset": 1,
                            "limit": 20,
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
                        "args": {"outcome": "success", "reason": "listed and read"},
                        "id": "t1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="tests 目录下有 test_fs_tools.py，用于测试 list_dir/read_file/grep。"),
        ]
    )
    out = run_manus(
        "看看 tests 里有什么，并读一下 test_fs_tools.py 开头。",
        model=model,
        max_steps=6,
        tools=tools,
    )
    assert out["status"] == "completed"
    logs = "\n".join(out["step_logs"])
    assert "list_dir" in logs and "read_file" in logs
    assert "test_fs_tools" in out["answer"] or "list_dir" in out["answer"]
