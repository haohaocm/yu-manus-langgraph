"""大模型客户端工厂。"""

import httpx
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings


def build_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """
    创建 OpenAI 兼容 Chat 客户端。

    base_url 指向本机 18000（SSH 转发到实验室 vLLM），不是官方 OpenAI。
    使用 ``trust_env=False``，避免本机 HTTP(S)_PROXY（如 Clash :7897）劫持 localhost 隧道导致 502。
    """
    s = settings or get_settings()
    http_client = httpx.Client(trust_env=False, timeout=120.0)
    return ChatOpenAI(
        model=s.model_name,
        api_key=s.openai_api_key,
        base_url=s.openai_base_url,
        temperature=0.2,
        http_client=http_client,
    )
