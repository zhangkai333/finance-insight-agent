"""Reproducible five-way RAG benchmark with honest optional-provider reporting.

The default run evaluates FTS5, hashing vector, hybrid RRF, and two optional
semantic/reranker variants. Missing external providers are recorded as
NOT_EXECUTED; no semantic score is fabricated from the hashing baseline.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from statistics import mean
from typing import Any, Callable

import sqlite_vec

from finance_insight.rag.embeddings import HashingEmbedding
from finance_insight.rag.hybrid import HybridRetriever


DEFAULT_QUERIES = [
    {"id": "rag_01", "query": "营业收入下降 主要原因", "stock_code": "002821", "year": 2024, "terms": ["营业收入", "原因"]},
    {"id": "rag_02", "query": "经营情况 业务变化", "stock_code": "300244", "year": 2024, "terms": ["经营", "业务"]},
    {"id": "rag_03", "query": "净利润下降 主要原因", "stock_code": "300347", "year": 2024, "terms": ["净利润", "原因"]},
    {"id": "rag_04", "query": "研发投入 经营情况", "stock_code": "301033", "year": 2024, "terms": ["研发", "经营"]},
    {"id": "rag_05", "query": "客户需求 市场变化", "stock_code": "301080", "year": 2024, "terms": ["客户", "市场"]},
]


def _filtered_details(con: sqlite3.Connection, ids: list[int], stock_code: str, year: int) -> list[dict[str, Any]]:
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = con.execute(
        f"""SELECT c.chunk_id, d.stock_code, d.report_year, c.page_number, c.content
            FROM document_chunks c JOIN documents d ON d.document_id=c.document_id
            WHERE c.chunk_id IN ({marks}) AND d.stock_code=? AND d.report_year=?""",
        [*ids, stock_code, year],
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    return [{"chunk_id": row[0], "stock_code": row[1], "report_year": row[2], "page_number": row[3], "content": row[4]} for row in (by_id[item] for item in ids if item in by_id)]


def fts_search(con: sqlite3.Connection, item: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    # FTS5's trigram tokenizer does not treat a natural-language phrase with
    # spaces as a useful Chinese query. Use the same fixed terms for every run
    # and let the report state that relevance is only a proxy.
    query = " OR ".join(item["terms"])
    try:
        rows = con.execute(
            """SELECT c.chunk_id FROM document_chunks_fts f
               JOIN document_chunks c ON c.chunk_id=f.chunk_id JOIN documents d ON d.document_id=c.document_id
               WHERE document_chunks_fts MATCH ? AND d.stock_code=? AND d.report_year=?
               ORDER BY bm25(document_chunks_fts) LIMIT ?""",
            [query, item["stock_code"], item["year"], top_k],
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    return _filtered_details(con, [row[0] for row in rows], item["stock_code"], item["year"])


def vector_search(con: sqlite3.Connection, item: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    embedding = HashingEmbedding()
    rows = con.execute(
        "SELECT chunk_id FROM chunk_vectors WHERE embedding MATCH ? AND k=?",
        [embedding.serialize(item["query"]), min(200, top_k * 30)],
    ).fetchall()
    # Fetch a wider candidate pool before metadata filtering, then apply the
    # common top-k cutoff. This mirrors the production hybrid retriever.
    details = _filtered_details(con, [row[0] for row in rows], item["stock_code"], item["year"])
    return details[:top_k]


def hybrid_search(db_path: Path, item: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    return HybridRetriever(db_path).search(item["query"], stock_codes=[item["stock_code"]], years=[item["year"]], top_k=top_k)


def proxy_relevance(row: dict[str, Any], terms: list[str]) -> bool:
    content = str(row.get("content", ""))
    return any(term in content for term in terms)


def measure(name: str, search: Callable[[dict[str, Any], int], list[dict[str, Any]]], queries: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in queries:
        started = time.perf_counter()
        try:
            hits = search(item, top_k)
            error = None
        except Exception as exc:
            hits = []
            error = type(exc).__name__
        latency = (time.perf_counter() - started) * 1000
        relevant_ranks = [index for index, hit in enumerate(hits, 1) if proxy_relevance(hit, item["terms"])]
        rows.append({
            "id": item["id"], "hits": len(hits), "hit": bool(hits),
            "proxy_relevant": bool(relevant_ranks),
            "first_relevant_rank": min(relevant_ranks) if relevant_ranks else None,
            "latency_ms": round(latency, 3), "error_type": error,
        })
    latencies = [row["latency_ms"] for row in rows]
    relevant = [row for row in rows if row["proxy_relevant"]]
    return {
        "status": "EXECUTED",
        "method": name,
        "cases": len(rows),
        "recall_at_k_proxy": round(len(relevant) / len(rows), 4) if rows else 0,
        "mrr_proxy": round(mean(1 / row["first_relevant_rank"] for row in relevant), 4) if relevant else 0,
        "hit_rate": round(sum(row["hit"] for row in rows) / len(rows), 4) if rows else 0,
        "latency_ms": {"average": round(mean(latencies), 3) if latencies else 0, "max": round(max(latencies), 3) if latencies else 0},
        "results": rows,
        "metric_note": "Proxy only: term overlap is not human-verified chunk relevance.",
    }


def run(db_path: Path, output: Path, top_k: int) -> dict[str, Any]:
    started = time.perf_counter()
    if not db_path.exists():
        raise FileNotFoundError(f"RAG database does not exist: {db_path}")
    con = sqlite3.connect(db_path)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    try:
        queries = DEFAULT_QUERIES
        methods: dict[str, Callable[[dict[str, Any], int], list[dict[str, Any]]]] = {
            "fts5": lambda item, k: fts_search(con, item, k),
            "hashing_vector": lambda item, k: vector_search(con, item, k),
            "fts5_plus_hashing_hybrid": lambda item, k: hybrid_search(db_path, item, k),
        }
        results = [measure(name, search, queries, top_k) for name, search in methods.items()]
        results.extend([
            {"status": "NOT_EXECUTED", "method": "semantic_embedding", "reason": "optional semantic embedding provider is not configured"},
            {"status": "NOT_EXECUTED", "method": "hybrid_plus_reranker", "reason": "optional reranker provider is not configured"},
        ])
    finally:
        con.close()
    payload = {
        "status": "PASS",
        "dataset": "fixed in scripts/benchmark_rag.py; replace with human-reviewed chunk labels before claiming Recall@K",
        "top_k": top_k,
        "embedding_baseline": "char-ngram-hashing-v1 (not semantic embedding)",
        "index": {
            "existing_index": "read-only benchmark; no rebuild performed",
            "database_size_bytes": db_path.stat().st_size,
            "benchmark_wall_time_ms": round((time.perf_counter() - started) * 1000, 3),
            "cost": "local CPU; no external API calls",
        },
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/rag.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/mvp_dataset/rag_benchmark.json"))
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    result = run(args.db, args.output, args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
