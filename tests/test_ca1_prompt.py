"""CA-1 S3：NEXT_STEP_PROMPT 含写文件路由关键字。"""

from app.prompts import NEXT_STEP_PROMPT


def test_ca1_prompt_write_routing_keywords():
    text = NEXT_STEP_PROMPT
    assert "write_file" in text
    assert "str_replace" in text
    assert "read_file" in text
    assert "full-file" in text.lower() or "entire file" in text.lower()
    assert "replace_all" in text
    assert "error:" in text
    assert "WORKSPACE_ROOT" in text
