import sqlite3
from pathlib import Path

import sqlite_vec

from finance_insight.config import settings
from finance_insight.intent_parser import parse_intent
from finance_insight.rag.hybrid import HybridRetriever
from finance_insight.tools import AnnualReportSearchTool


def _vector_count(db_path: Path) -> int:
    con = sqlite3.connect(db_path)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    try:
        return con.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
    finally:
        con.close()


def test_vector_index_covers_all_chunks():
    db_path = settings.rag_db
    con = sqlite3.connect(db_path)
    try:
        chunk_count = con.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    finally:
        con.close()
    assert chunk_count > 0
    assert _vector_count(db_path) == chunk_count


def test_hybrid_retriever_returns_traceable_results():
    retriever = HybridRetriever(settings.rag_db)
    rows = retriever.search("主要原因", stock_codes=["002821"], years=[2024], top_k=3)
    assert rows
    assert all(row["retrieval_mode"] == "hybrid_weighted_rrf" for row in rows)
    assert all(row["embedding_provider"] == "char-ngram-hashing-v1" for row in rows)
    assert all(row["page_number"] > 0 and row["source_file"] for row in rows)


def test_rag_tool_prefers_hybrid_search():
    intent = parse_intent("结合年报解释凯莱英2024年净利润下降原因")
    result = AnnualReportSearchTool().run(intent, query="主要原因", top_k=2)
    assert result.status == "success"
    assert result.data["retrieval_mode"] == "hybrid_weighted_rrf"
    assert result.data["embedding_provider"] == "char-ngram-hashing-v1"
    assert result.fallback_used is False
