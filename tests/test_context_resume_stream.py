"""续聊：同 thread_id 第二轮应把历史带进 reason 投影。"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.config import get_settings
from app.graph.checkpointing import reset_checkpointer_singleton_for_tests
from app.manus import iter_manus_events
from app.tools.local_tools import get_phase1_tools


class HistoryAwareModel(BaseChatModel):
    """检查投影历史里是否出现过「我叫X」；用于验证续聊上下文。"""

    call_count: int = 0
    saw_name_in_history: bool = False
    last_human_texts: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "history-aware"

    def _generate(self, messages: list, stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        """根据入参 messages 决定回复；记录是否见过自称。"""
        self.call_count += 1
        humans = [
            (m.content or "")
            for m in messages
            if isinstance(m, HumanMessage)
        ]
        self.last_human_texts = list(humans)
        joined = "\n".join(humans)
        if "郁皓宇" in joined or "我叫" in joined:
            # 首轮自我介绍或历史里已有名字
            if "我叫什么" in joined or "叫什么名字" in joined:
                self.saw_name_in_history = "郁皓宇" in joined
                text = "你叫郁皓宇。" if self.saw_name_in_history else "还不知道你的名字。"
            else:
                text = "你好，郁皓宇，已记下你的名字。"
        else:
            text = "还不知道你的名字。"
        # 无 tool_calls → 走 text-only 结束
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def bind_tools(self, tools, **kwargs):
        return self


def test_second_turn_sees_prior_name(tmp_path, monkeypatch):
    """第一轮自我介绍后，同 thread 问名字应能在历史中看到「郁皓宇」。"""
    db = tmp_path / "ctx.sqlite"
    monkeypatch.setenv("CHECKPOINT_ENABLED", "true")
    monkeypatch.setenv("CHECKPOINT_SQLITE_PATH", str(db))
    get_settings.cache_clear()
    reset_checkpointer_singleton_for_tests()

    model = HistoryAwareModel()
    events1 = list(
        iter_manus_events(
            "你好我叫郁皓宇",
            model=model,
            max_steps=5,
            tools=get_phase1_tools(),
            use_checkpoint=True,
            checkpoint_path=str(db),
            persist_event_log=False,
        )
    )
    tid = events1[0]["thread_id"]
    assert events1[-1]["type"] == "done"

    model2 = HistoryAwareModel()
    events2 = list(
        iter_manus_events(
            "我叫什么名字",
            model=model2,
            max_steps=5,
            tools=get_phase1_tools(),
            thread_id=tid,
            use_checkpoint=True,
            checkpoint_path=str(db),
            persist_event_log=False,
        )
    )
    assert events2[0]["thread_id"] == tid
    assert model2.saw_name_in_history is True
    assert "郁皓宇" in (events2[-1].get("answer") or "")
