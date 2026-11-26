"""Phase 3: FastAPI contract tests (no remote LLM)."""

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import app
from app.manus import run_manus
from app.tools.local_tools import get_phase1_tools
from tests.test_phase1_manus_graph import ScriptedChatModel


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "UP"
    assert body["app"] == "yu-manus-langgraph"


def test_agent_run_get_no_longer_405():
    r = client.get("/agent/run")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "POST" in body["hint"]


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "YuManus" in r.text


def test_agent_run_validation():
    r = client.post("/agent/run", json={"message": ""})
    assert r.status_code == 422


def test_agent_run_with_monkeypatch(monkeypatch):
    def fake_run(message, max_steps=None, **kwargs):
        assert message == "hello"
        return {
            "answer": "你好！",
            "final_answer": "你好！",
            "status": "completed",
            "end_reason": "text reply without tools",
            "steps": 1,
            "step_logs": ["step1 : think=hi tools=[] → completed", "summarize : 你好！"],
            "messages": [],
        }

    monkeypatch.setattr("app.main.run_manus", fake_run)
    r = client.post(
        "/agent/run",
        json={"message": "hello", "session_id": "s1", "max_steps": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["end_reason"] == "text reply without tools"
    assert body["session_id"] == "s1"
    assert body["steps"] == 1
    assert body["answer"] == "你好！"
    assert body["final_answer"] == "你好！"


def test_run_manus_still_works_offline():
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="ok"),
            AIMessage(content="pong"),
        ]
    )
    out = run_manus("ping", model=model, max_steps=2, tools=get_phase1_tools())
    assert out["status"] == "completed"
    assert out["answer"] == "pong"
