"""EMB-1：embedding（向量嵌入）——仅 OpenAI 兼容 HTTP（实验室 bge）。不做 stub 回退。"""

from __future__ import annotations

import math
from typing import Protocol

import httpx

from app.config import Settings, get_settings


class EmbeddingError(RuntimeError):
    """embedding 调用失败（连接、HTTP、响应格式等），信息面向排错。"""


class Embedder(Protocol):
    """向量化接口：texts → 等维向量列表。"""

    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return vec
    return [x / norm for x in vec]


class HttpOpenAIEmbedder:
    """OpenAI 兼容 ``/v1/embeddings``（实验室 bge 经本机隧道 ``:18001``）。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "EMPTY",
        model: str = "bge-m3",
        timeout: float = 60.0,
        dim: int | None = None,
        max_batch: int = 4,
        max_chars_per_text: int = 2000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "EMPTY"
        self.model = model
        self.timeout = timeout
        self._dim = dim
        # 默认取「与 Qwen 共存」探针下的稳妥值；更大可改 .env，OOM 时仍会拆半重试
        self.max_batch = int(max_batch)
        self.max_chars_per_text = int(max_chars_per_text)
        self.name = f"http:{model}"

    @property
    def dim(self) -> int:
        if self._dim is None:
            raise RuntimeError("dim unknown until first successful embed()")
        return self._dim

    def ping(self) -> dict:
        """轻量探测：GET ``/models``，再 embed 一句。"""
        models_url = f"{self.base_url}/models"
        try:
            with httpx.Client(timeout=min(self.timeout, 15.0), trust_env=False) as client:
                resp = client.get(models_url, headers={"Authorization": f"Bearer {self.api_key}"})
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "detail": f"GET {models_url} -> HTTP {resp.status_code}: {resp.text[:300]}",
                        "dim": self._dim,
                    }
                body = resp.json()
                ids = [x.get("id") for x in (body.get("data") or [])]
                if self.model not in ids and ids:
                    detail = f"models ok but {self.model!r} not in {ids}; will still try embed"
                else:
                    detail = f"models ok: {ids}"
        except httpx.RequestError as exc:
            return {
                "ok": False,
                "detail": f"cannot reach embedding server at {self.base_url}: {exc}",
                "dim": self._dim,
            }

        try:
            vecs = self.embed(["ping"])
            return {"ok": True, "detail": detail, "dim": len(vecs[0]) if vecs else self._dim}
        except EmbeddingError as exc:
            return {"ok": False, "detail": f"{detail}; embed failed: {exc}", "dim": self._dim}

    def _validate_inputs(self, texts: list[str]) -> list[str]:
        """校验单条文本；不再因「总数 > max_batch」整批拒绝（由 embed 自动分批）。"""
        if not texts:
            raise EmbeddingError("embed input is empty: pass a non-empty list of strings")
        cleaned: list[str] = []
        for i, t in enumerate(texts):
            if t is None:
                raise EmbeddingError(f"embed input[{i}] is None")
            s = str(t)
            if not s.strip():
                raise EmbeddingError(f"embed input[{i}] is blank; refuse empty strings")
            # 超长则截断再 embed（索引场景）；避免单条打爆 GPU
            if len(s) > self.max_chars_per_text:
                s = s[: self.max_chars_per_text]
            cleaned.append(s)
        return cleaned

    def _embed_one_batch(self, batch: list[str]) -> list[list[float]]:
        """向 bge 发送一批并返回等长向量。

        若服务端 500（常见 CUDA OOM），自动对半分批重试，直到单条仍失败才抛错。
        """
        if not batch:
            return []
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "input": batch}
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False) as client:
                resp = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise EmbeddingError(
                f"embedding timeout after {self.timeout}s calling {url} (model={self.model})"
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingError(
                f"embedding connection failed to {url} (model={self.model}): {exc}. "
                "Open Xshell tunnel 18001->8001 and ensure bge is running before EMB tests."
            ) from exc

        if resp.status_code >= 500 and len(batch) > 1:
            # 显存不足时常见；拆半重试
            mid = len(batch) // 2
            return self._embed_one_batch(batch[:mid]) + self._embed_one_batch(batch[mid:])

        if resp.status_code >= 400:
            raise EmbeddingError(
                f"embedding HTTP {resp.status_code} from {url} (model={self.model}): {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise EmbeddingError(f"embedding response is not JSON from {url}: {resp.text[:300]}") from exc

        rows = data.get("data")
        if not isinstance(rows, list) or not rows:
            raise EmbeddingError(f"embedding response missing data[] from {url}: keys={list(data)[:12]}")

        try:
            items = sorted(rows, key=lambda x: int(x["index"]))
            vectors = [list(map(float, row["embedding"])) for row in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(f"embedding response schema invalid: {exc}") from exc

        if len(vectors) != len(batch):
            raise EmbeddingError(
                f"embedding count mismatch: sent {len(batch)} got {len(vectors)}"
            )
        return vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        """向量化；超过 max_batch 时自动按批请求再拼接（全仓索引必需）。"""
        cleaned = self._validate_inputs(texts)
        batch_size = max(1, int(self.max_batch))
        all_vectors: list[list[float]] = []
        for start in range(0, len(cleaned), batch_size):
            batch = cleaned[start : start + batch_size]
            all_vectors.extend(self._embed_one_batch(batch))

        if self._dim is None and all_vectors:
            self._dim = len(all_vectors[0])
        for i, v in enumerate(all_vectors):
            if self._dim is not None and len(v) != self._dim:
                raise EmbeddingError(
                    f"inconsistent embedding dim at index {i}: {len(v)} vs expected {self._dim}"
                )
        return [_l2_normalize(v) for v in all_vectors]


def get_embedder(settings: Settings | None = None) -> HttpOpenAIEmbedder:
    """
    返回 bge HTTP embedder。

    约定：不做 stub 回退；``embedding_backend=stub`` 直接报错。
    跑 EMB 相关测试前必须打开隧道 ``18001→8001``。
    """
    s = settings or get_settings()
    backend = (s.embedding_backend or "http").strip().lower()
    if backend == "stub":
        raise EmbeddingError(
            "stub embedding is disabled. Use EMBEDDING_BACKEND=http (bge) "
            "and open tunnel 18001->8001. Silent stub fallback is not allowed."
        )
    if backend not in {"http", "openai", "bge"}:
        raise ValueError(f"unknown embedding_backend: {backend!r} (use http)")
    return HttpOpenAIEmbedder(
        base_url=s.embedding_base_url,
        api_key=s.embedding_api_key or s.openai_api_key,
        model=s.embedding_model,
        timeout=float(s.embedding_timeout),
        max_batch=int(getattr(s, "embedding_max_batch", 4) or 4),
        max_chars_per_text=int(getattr(s, "embedding_max_chars", 2000) or 2000),
    )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度；向量宜已 L2 归一化。"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)
