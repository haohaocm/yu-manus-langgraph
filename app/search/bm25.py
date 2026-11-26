"""极简 BM25 Okapi（词法检索打分），无第三方依赖。"""

from __future__ import annotations

import math
from collections import Counter


class BM25Okapi:
    """
    标准 Okapi BM25。

    参数默认 k1=1.5、b=0.75（常见经验值）。
    """

    def __init__(
        self,
        corpus_tokens: list[list[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1 = float(k1)
        self.b = float(b)
        self.corpus_tokens = corpus_tokens
        self.n_docs = len(corpus_tokens)
        self.doc_len = [len(doc) for doc in corpus_tokens]
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0

        df: Counter[str] = Counter()
        self.tfs: list[Counter[str]] = []
        for doc in corpus_tokens:
            tf = Counter(doc)
            self.tfs.append(tf)
            for term in tf:
                df[term] += 1
        self.df = dict(df)
        self.idf = {
            term: math.log(1.0 + (self.n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in self.df.items()
        }

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        """对语料中每个文档返回 BM25 分数。"""
        if self.n_docs == 0:
            return []
        scores = [0.0] * self.n_docs
        # 去重查询词仍按出现计一次即可（经典 BM25 对 query 侧常按 unique）
        q_terms = list(dict.fromkeys(t for t in query_tokens if t))
        for term in q_terms:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf_map in enumerate(self.tfs):
                freq = tf_map.get(term, 0)
                if freq == 0:
                    continue
                dl = self.doc_len[i]
                denom = freq + self.k1 * (1.0 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * (freq * (self.k1 + 1.0) / denom)
        return scores
