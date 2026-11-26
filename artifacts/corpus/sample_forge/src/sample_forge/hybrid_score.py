"""Tiny hybrid scoring helpers for teaching demos."""

from __future__ import annotations


def blend(bm25: float, embedding: float, alpha: float = 0.5) -> float:
    """alpha weights embedding; (1-alpha) weights bm25."""
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be in [0, 1]")
    return (1.0 - alpha) * bm25 + alpha * embedding


def min_max_norm(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]
