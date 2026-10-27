from __future__ import annotations

from typing import Any, Protocol


class Reranker(Protocol):
    name: str

    def rerank(
        self,
        rows: list[dict[str, Any]],
        *,
        terms: list[str],
        stock_codes: list[str],
        years: list[int],
        top_k: int,
    ) -> list[dict[str, Any]]: ...


class LexicalMetadataReranker:
    """Deterministic fallback for environments without a cross-encoder."""

    name = "lexical-metadata-v1"

    def __init__(self, max_chars: int = 200):
        self.max_chars = max_chars

    def rerank(
        self,
        rows: list[dict[str, Any]],
        *,
        terms: list[str],
        stock_codes: list[str],
        years: list[int],
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for row in rows:
            content = str(row.get("content", ""))[: self.max_chars]
            matched = [term for term in terms if term in content]
            coverage = len(matched) / max(1, len(terms))
            metadata = 0.0
            if str(row.get("stock_code", "")) in stock_codes:
                metadata += 0.1
            if int(row.get("report_year") or 0) in years:
                metadata += 0.1
            retrieval_score = float(row.get("fusion_score") or row.get("score") or 0.0)
            if retrieval_score < 0:
                retrieval_score = 1.0 / (1.0 + abs(retrieval_score))
            item = dict(row)
            item["matched_terms"] = matched
            item["term_coverage"] = round(coverage, 4)
            item["rerank_score"] = round(0.65 * coverage + metadata + 0.15 * retrieval_score, 6)
            ranked.append(item)
        return sorted(ranked, key=lambda item: item["rerank_score"], reverse=True)[:top_k]


def evidence_sufficiency(rows: list[dict[str, Any]], terms: list[str]) -> tuple[float, bool]:
    if not rows:
        return 0.0, False
    covered = {term for row in rows for term in terms if term in str(row.get("content", ""))}
    coverage = len(covered) / max(1, len(terms))
    source_bonus = min(0.2, len({row.get("page_number") for row in rows}) * 0.05)
    score = round(min(1.0, coverage + source_bonus), 4)
    return score, score >= 0.35
