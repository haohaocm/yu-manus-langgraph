"""EMB 测试约定：必须开隧道 18001→8001；禁止 stub。"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.search.embed import EmbeddingError, HttpOpenAIEmbedder, get_embedder


def require_bge_embedder() -> HttpOpenAIEmbedder:
    """测 EMB 前探测 bge；失败则 pytest.fail（不静默改 stub）。"""
    settings = Settings(embedding_backend="http", workspace_root=".")
    try:
        emb = get_embedder(settings)
    except EmbeddingError as exc:
        pytest.fail(f"EMB tests require bge (tunnel 18001->8001): {exc}")
    ping = emb.ping()
    if not ping.get("ok"):
        pytest.fail(
            "EMB tests require open tunnel 18001->8001 and running bge. "
            f"detail={ping.get('detail')}"
        )
    return emb
