from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

import sqlite_vec

from finance_insight.rag.embeddings import HashingEmbedding


class HybridRetriever:
    """FTS5 + sqlite-vec 的 Reciprocal Rank Fusion 检索器。"""

    def __init__(self, db_path: Path, embedding: HashingEmbedding | None = None):
        self.db_path = db_path
        self.embedding = embedding or HashingEmbedding()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        return con

    def available(self) -> bool:
        if not self.db_path.exists():
            return False
        con = self._connect()
        try:
            row = con.execute("SELECT 1 FROM sqlite_master WHERE name='chunk_vectors'").fetchone()
            return row is not None
        finally:
            con.close()

    def search(
        self,
        query: str,
        *,
        stock_codes: list[str],
        years: list[int],
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        con = self._connect()
        try:
            fts_rows: list[sqlite3.Row] = []
            try:
                fts_rows = con.execute(
                    """SELECT c.chunk_id, bm25(document_chunks_fts) AS score
                       FROM document_chunks_fts f
                       JOIN document_chunks c ON c.chunk_id=f.chunk_id
                       JOIN documents d ON d.document_id=c.document_id
                       WHERE document_chunks_fts MATCH ?
                         AND d.stock_code IN ({codes}) AND d.report_year IN ({years})
                       ORDER BY score LIMIT ?""".format(
                           codes=",".join("?" for _ in stock_codes),
                           years=",".join("?" for _ in years),
                       ),
                    [query, *stock_codes, *years, top_k * 4],
                ).fetchall()
            except sqlite3.OperationalError:
                pass

            vector_rows = con.execute(
                "SELECT chunk_id, distance FROM chunk_vectors WHERE embedding MATCH ? AND k = ?",
                [self.embedding.serialize(query), min(200, top_k * 30)],
            ).fetchall()
            vector_ids = [row["chunk_id"] for row in vector_rows]
            allowed_vector_ids: set[int] = set()
            if vector_ids:
                sql = """SELECT c.chunk_id FROM document_chunks c
                         JOIN documents d ON d.document_id=c.document_id
                         WHERE c.chunk_id IN ({ids}) AND d.stock_code IN ({codes}) AND d.report_year IN ({years})""".format(
                    ids=",".join("?" for _ in vector_ids),
                    codes=",".join("?" for _ in stock_codes),
                    years=",".join("?" for _ in years),
                )
                allowed_vector_ids = {
                    row[0] for row in con.execute(sql, [*vector_ids, *stock_codes, *years]).fetchall()
                }

            fused: dict[int, float] = defaultdict(float)
            for rank, row in enumerate(fts_rows, start=1):
                fused[row["chunk_id"]] += 1.0 / (60 + rank)
            filtered_vectors = [row for row in vector_rows if row["chunk_id"] in allowed_vector_ids]
            for rank, row in enumerate(filtered_vectors, start=1):
                fused[row["chunk_id"]] += 1.0 / (60 + rank)
            ids = [item[0] for item in sorted(fused.items(), key=lambda item: item[1], reverse=True)[:top_k]]
            if not ids:
                return []
            details = con.execute(
                """SELECT d.stock_code,d.company_name,d.report_year,d.source_file,
                          c.page_number,c.chunk_id,c.content
                   FROM document_chunks c JOIN documents d ON d.document_id=c.document_id
                   WHERE c.chunk_id IN ({ids})""".format(ids=",".join("?" for _ in ids)),
                ids,
            ).fetchall()
            by_id = {row["chunk_id"]: dict(row) for row in details}
            results = []
            for chunk_id in ids:
                item = by_id[chunk_id]
                item["score"] = fused[chunk_id]
                item["retrieval_mode"] = "hybrid_rrf"
                item["embedding_provider"] = self.embedding.name
                results.append(item)
            return results
        finally:
            con.close()
