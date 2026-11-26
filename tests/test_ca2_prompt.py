"""CA-2：NEXT_STEP_PROMPT 含 run_shell 路由。"""

from app.prompts import NEXT_STEP_PROMPT


def test_ca2_prompt_run_shell_keywords():
    text = NEXT_STEP_PROMPT
    assert "run_shell" in text
    assert "exit_code" in text
    assert "pytest" in text.lower() or "tests" in text.lower()
