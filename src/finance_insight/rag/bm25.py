from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


def tokenize(text: str) -> list[str]:
    try:
        import jieba
    except ImportError as exc:  # pragma: no cover - optional production dependency
        raise RuntimeError("jieba 未安装，无法启用 production BM25") from exc
    return [
        token.strip().lower()
        for token in jieba.cut(text)
        if token.strip() and not re.fullmatch(r"\W+", token)
    ]


def bm25_search(
    query: str,
    rows: list[dict[str, Any]],
    *,
    top_k: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[dict[str, Any]]:
    query_terms = list(dict.fromkeys(tokenize(query)))
    documents = [tokenize(str(row.get("content", ""))) for row in rows]
    if not query_terms or not documents:
        return []
    average_length = sum(map(len, documents)) / max(1, len(documents))
    frequencies = Counter(term for terms in documents for term in set(terms))
    ranked: list[dict[str, Any]] = []
    for row, terms in zip(rows, documents, strict=True):
        counts = Counter(terms)
        score = 0.0
        for term in query_terms:
            document_frequency = frequencies[term]
            if not document_frequency:
                continue
            inverse_frequency = math.log(
                1 + (len(documents) - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            frequency = counts[term]
            denominator = frequency + k1 * (1 - b + b * len(terms) / max(1.0, average_length))
            score += inverse_frequency * frequency * (k1 + 1) / denominator
        if score > 0:
            item = dict(row)
            item["bm25_score"] = score
            ranked.append(item)
    return sorted(ranked, key=lambda item: item["bm25_score"], reverse=True)[:top_k]
