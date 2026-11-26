"""检索用简易 tokenizer（分词）：英文按词，中文按字。"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """
    把文本拆成 BM25 用的 token 列表。

    - ASCII 标识符：整词小写
    - 连续汉字：拆成单字（Demo 够用，不引入分词库）
    """
    if not text:
        return []
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        piece = m.group(0)
        if piece.isascii():
            out.append(piece.lower())
        else:
            out.extend(list(piece))
    return out
