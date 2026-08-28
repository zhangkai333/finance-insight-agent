"""Search the Phase 3 local RAG index and return citation metadata."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--stock-code")
    parser.add_argument("--year", type=int)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    try:
        sql = """SELECT d.stock_code, d.company_name, d.report_year, d.title,
                         d.source_file, c.page_number, c.chunk_id, c.content,
                         bm25(document_chunks_fts) AS score
                  FROM document_chunks_fts f
                  JOIN document_chunks c ON c.chunk_id = f.chunk_id
                  JOIN documents d ON d.document_id = c.document_id
                  WHERE document_chunks_fts MATCH ?"""
        params: list[object] = [args.query]
        if args.stock_code:
            sql += " AND d.stock_code = ?"
            params.append(args.stock_code)
        if args.year:
            sql += " AND d.report_year = ?"
            params.append(args.year)
        sql += " ORDER BY score LIMIT ?"
        params.append(args.top_k)
        try:
            rows = [dict(row) for row in con.execute(sql, params).fetchall()]
        except sqlite3.OperationalError:
            # Fallback for short Chinese terms or FTS syntax that cannot be tokenized.
            like_sql = """SELECT d.stock_code, d.company_name, d.report_year, d.title,
                                  d.source_file, c.page_number, c.chunk_id, c.content,
                                  NULL AS score
                           FROM document_chunks c
                           JOIN documents d ON d.document_id = c.document_id
                           WHERE c.content LIKE ?"""
            like_params: list[object] = [f"%{args.query}%"]
            if args.stock_code:
                like_sql += " AND d.stock_code = ?"
                like_params.append(args.stock_code)
            if args.year:
                like_sql += " AND d.report_year = ?"
                like_params.append(args.year)
            like_sql += " LIMIT ?"
            like_params.append(args.top_k)
            rows = [dict(row) for row in con.execute(like_sql, like_params).fetchall()]
    finally:
        con.close()
    payload = {"query": args.query, "results": rows, "status": "PASS" if rows else "NO_HIT"}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
