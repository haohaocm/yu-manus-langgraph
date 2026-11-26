"""Phase 0: scaffold / config / import smoke tests (no LLM required)."""

from app import __version__
from app.config import Settings, get_settings


def test_version():
    assert __version__ == "0.1.0"


def test_settings_defaults_from_env():
    get_settings.cache_clear()
    s = get_settings()
    assert isinstance(s, Settings)
    assert s.api_port == 8200
    assert s.max_steps == 10
    assert isinstance(s.mcp_enabled, bool)  # 具体值由 .env 决定（联调时常为 true）
    assert "18000" in s.openai_base_url
    assert s.openai_api_key


def test_llm_factory_builds_without_network():
    from app.llm import build_chat_model

    get_settings.cache_clear()
    model = build_chat_model()
    assert model.model_name or model.model
