"""Pure unit tests for ending strategy helpers."""

from app.graph.ending import (
    on_budget_exceeded,
    on_cancelled,
    on_terminate,
    on_text_only_finish,
    parse_terminate_from_tool_content,
    should_end,
)


def test_on_terminate_success_and_abandon():
    ok = on_terminate(outcome="success", reason="sum done")
    assert ok["status"] == "completed"
    assert ok["end_reason"] == "sum done"

    give_up = on_terminate(outcome="abandon", reason="no web search")
    assert give_up["status"] == "abandoned"
    assert "no web search" in give_up["end_reason"]


def test_on_text_and_budget_and_cancelled():
    text = on_text_only_finish(thought="hello")
    assert text["status"] == "completed"

    budget = on_budget_exceeded(step=11, max_steps=10)
    assert budget["status"] == "budget_exceeded"
    assert "max_steps=10" in budget["end_reason"]

    cancel = on_cancelled(reason="stop clicked")
    assert cancel["status"] == "cancelled"
    assert should_end({"status": "cancelled"}) is True


def test_should_end_matrix():
    assert should_end({"status": "running"}) is False
    for s in ("completed", "abandoned", "budget_exceeded", "cancelled", "finished", "error"):
        assert should_end({"status": s}) is True


def test_parse_terminate_content():
    assert parse_terminate_from_tool_content("nope") is None
    assert parse_terminate_from_tool_content("terminated:outcome=abandon:reason=cannot") == (
        "abandon",
        "cannot",
    )
