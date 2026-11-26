"""CA-6 S1：HITL 策略引擎单测（不启图、不写盘）。"""

from app.hitl.policy import HitlDecision, classify_tool_call


def test_readonly_allow_auto():
    """只读工具应自动放行。"""
    for name in ("read_file", "list_dir", "grep", "semantic_search"):
        v = classify_tool_call(name, {"path": "a.txt"})
        assert v.decision == HitlDecision.ALLOW_AUTO, name


def test_write_tools_need_approve():
    """写文件类一律需要人工批准。"""
    v1 = classify_tool_call("write_file", {"path": "outputs/a.txt", "content": "hi"})
    assert v1.decision == HitlDecision.NEED_APPROVE
    assert v1.risk == "write"
    v2 = classify_tool_call("str_replace", {"path": "x.py", "old": "a", "new": "b"})
    assert v2.decision == HitlDecision.NEED_APPROVE


def test_shell_blacklist_hard_deny():
    """黑名单命令硬拒绝，不进入审批。"""
    v = classify_tool_call("run_shell", {"command": "rm -rf /tmp/demo"})
    assert v.decision == HitlDecision.HARD_DENY
    assert v.risk == "blocked"
    assert "blacklist" in v.reason


def test_shell_normal_need_approve():
    """普通 shell 需要批准。"""
    v = classify_tool_call("run_shell", {"command": "python -c \"print(1)\""})
    assert v.decision == HitlDecision.NEED_APPROVE
    assert v.risk == "shell"


def test_hitl_disabled_bypasses_all():
    """HITL_ENABLED=false 时全部自动（回滚/单测旁路）。"""
    v = classify_tool_call(
        "write_file",
        {"path": "x", "content": "y"},
        hitl_enabled=False,
    )
    assert v.decision == HitlDecision.ALLOW_AUTO


def test_terminate_allow_auto():
    """结束工具不走审批。"""
    v = classify_tool_call("terminate", {"outcome": "success", "reason": "done"})
    assert v.decision == HitlDecision.ALLOW_AUTO


def test_unknown_tool_defaults_to_approve():
    """未知工具默认要批，避免误放行。"""
    v = classify_tool_call("mysterious_tool", {})
    assert v.decision == HitlDecision.NEED_APPROVE
