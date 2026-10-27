from __future__ import annotations

from dataclasses import replace

import pytest

from finance_insight.config import settings

pytest.importorskip("chromadb")
pytest.importorskip("jieba")

from finance_insight.rag.chroma_hybrid import ChromaHybridRetriever  # noqa: E402


def test_chroma_hashing_fallback_indexes_and_searches(tmp_path):
    config = replace(
        settings,
        rag_backend="chroma",
        chroma_path=tmp_path / "chroma",
        chroma_collection="test_demo",
        embedding_api_key=None,
    )
    retriever = ChromaHybridRetriever(config)

    assert retriever.index_sqlite() > 0
    rows = retriever.search(
        "营业收入变化主要原因",
        stock_codes=["002821"],
        years=[2024],
        top_k=2,
    )

    assert rows
    assert retriever.embedding_fallback is True
    assert rows[0]["retrieval_mode"] == "chroma_hashing_bm25"
    assert rows[0]["page_number"] > 0
