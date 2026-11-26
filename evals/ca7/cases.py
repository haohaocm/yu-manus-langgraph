"""
CA-7 固定题定义。

每题：id / 标题 / 模式（offline|live）/ 说明 / 运行函数名。
离线题用假模型，可重复；live 题打真 Qwen（需 18000）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EvalResult:
    """单题结果。"""

    case_id: str
    title: str
    passed: bool
    detail: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalCase:
    """固定题元数据。"""

    id: str
    title: str
    mode: str  # offline | live
    description: str
    run: Callable[..., EvalResult]


def get_cases() -> list[EvalCase]:
    """返回全部 CA-7 题（延迟导入 runner 内实现，避免环依赖）。"""
    from evals.ca7 import runners

    return [
        EvalCase(
            id="E1_add_terminate",
            title="假模型：add 后 terminate",
            mode="offline",
            description="2+3=5，status=completed，步数合理",
            run=runners.run_e1_add_terminate,
        ),
        EvalCase(
            id="E2_hitl_approve_write",
            title="假模型：HITL 批准写文件",
            mode="offline",
            description="未批不落盘；approve 后 outputs/ca7_e2.txt 内容正确",
            run=runners.run_e2_hitl_approve_write,
        ),
        EvalCase(
            id="E3_hitl_reject_write",
            title="假模型：HITL 拒绝写文件",
            mode="offline",
            description="reject 后文件不存在，图仍能 done",
            run=runners.run_e3_hitl_reject_write,
        ),
        EvalCase(
            id="E4_shell_blacklist",
            title="策略：shell 黑名单 hard_deny",
            mode="offline",
            description="rm -rf 类命令硬拒",
            run=runners.run_e4_shell_blacklist,
        ),
        EvalCase(
            id="E5_context_resume",
            title="假模型：同 thread 续聊记名字",
            mode="offline",
            description="先自我介绍再问名字，历史可见",
            run=runners.run_e5_context_resume,
        ),
        EvalCase(
            id="E6_live_chat",
            title="真模型：短问答冒烟",
            mode="live",
            description="不问工具；status 非 error；有非空 answer",
            run=runners.run_e6_live_chat,
        ),
        EvalCase(
            id="E7_live_write_no_hitl",
            title="真模型：关 HITL 写文件",
            mode="live",
            description="HITL_ENABLED=false；写出 outputs/ca7_e7.txt",
            run=runners.run_e7_live_write_no_hitl,
        ),
    ]
