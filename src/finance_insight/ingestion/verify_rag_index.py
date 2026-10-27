"""Validate the Phase 3 annual-report index and citation fields."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def search(
    con: sqlite3.Connection,
    query: str,
    stock_code: str | None = None,
    year: int | None = None,
    top_k: int = 5,
):
    sql = """SELECT d.stock_code, d.company_name, d.report_year, d.source_file,
                     c.page_number, c.chunk_id, c.content
              FROM document_chunks_fts f
              JOIN document_chunks c ON c.chunk_id = f.chunk_id
              JOIN documents d ON d.document_id = c.document_id
              WHERE document_chunks_fts MATCH ?"""
    params: list[object] = [query]
    if stock_code:
        sql += " AND d.stock_code = ?"
        params.append(stock_code)
    if year:
        sql += " AND d.report_year = ?"
        params.append(year)
    sql += " ORDER BY bm25(document_chunks_fts) LIMIT ?"
    params.append(top_k)
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-documents", type=int)
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--expected-chunks", type=int)
    args = parser.parse_args()
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    try:
        counts = {
            "documents": con.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "pages_indexed": con.execute("SELECT SUM(page_count) FROM documents").fetchone()[0],
            "chunks": con.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0],
            "fts_rows": con.execute("SELECT COUNT(*) FROM document_chunks_fts").fetchone()[0],
        }
        tests = {
            "company_filtered_reason_search": search(con, "主要原因", "002821", 2024, 3),
            "company_filtered_rd_search": search(con, "研发投入", "002821", 2024, 3),
            "cross_company_search": search(con, "研发投入", None, 2024, 10),
        }
    finally:
        con.close()
    expectations = {
        "documents": args.expected_documents,
        "pages_indexed": args.expected_pages,
        "chunks": args.expected_chunks,
    }
    mismatches = {
        key: (counts[key], expected)
        for key, expected in expectations.items()
        if expected is not None and counts[key] != expected
    }
    if mismatches:
        raise SystemExit(f"索引计数不符合预期: {mismatches}")
    if any(counts[key] <= 0 for key in ("documents", "pages_indexed", "chunks")):
        raise SystemExit(f"索引为空: {counts}")
    if counts["chunks"] != counts["fts_rows"]:
        raise SystemExit(f"FTS 与 chunk 数量不一致: {counts}")
    for test_name, rows in tests.items():
        if not rows:
            raise SystemExit(f"检索无命中: {test_name}")
        for row in rows:
            if not row["source_file"] or row["page_number"] <= 0 or not row["content"]:
                raise SystemExit(f"检索结果缺少溯源字段: {test_name}, {row}")
    if any(row["stock_code"] != "002821" for row in tests["company_filtered_reason_search"]):
        raise SystemExit("公司过滤条件未生效")
    payload = {"counts": counts, "tests": tests, "status": "PASS"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "counts": counts,
                "test_hit_counts": {k: len(v) for k, v in tests.items()},
                "status": "PASS",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
