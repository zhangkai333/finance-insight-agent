from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from finance_insight.config import Settings, settings
from finance_insight.rag.bm25 import bm25_search
from finance_insight.rag.semantic import OpenAICompatibleEmbedding


class ChromaHybridRetriever:
    """Optional BGE-M3 + Chroma + jieba BM25 retrieval backend."""

    def __init__(self, config: Settings = settings):
        try:
            import chromadb
            import jieba  # noqa: F401
        except ImportError as exc:  # pragma: no cover - optional production dependency
            raise RuntimeError("production RAG 需要安装 chromadb 和 jieba") from exc
        self.config = config
        self.embedding = OpenAICompatibleEmbedding(config)
        self.client = chromadb.PersistentClient(path=str(config.chroma_path))
        self.collection = self.client.get_or_create_collection(
            name=config.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def available(self) -> bool:
        return self.collection.count() > 0

    def _corpus(self, stock_codes: list[str], years: list[int]) -> list[dict[str, Any]]:
        with sqlite3.connect(self.config.rag_db) as connection:
            connection.row_factory = sqlite3.Row
            code_marks = ",".join("?" for _ in stock_codes)
            year_marks = ",".join("?" for _ in years)
            rows = connection.execute(
                f"""SELECT d.stock_code,d.company_name,d.report_year,d.source_file,
                           c.page_number,c.chunk_id,c.content
                    FROM document_chunks c JOIN documents d ON d.document_id=c.document_id
                    WHERE d.stock_code IN ({code_marks}) AND d.report_year IN ({year_marks})""",
                [*stock_codes, *years],
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _normalise(values: dict[int, float], *, distance: bool = False) -> dict[int, float]:
        if not values:
            return {}
        transformed = {key: (1.0 - value if distance else value) for key, value in values.items()}
        low, high = min(transformed.values()), max(transformed.values())
        if high == low:
            return {key: 1.0 for key in transformed}
        return {key: (value - low) / (high - low) for key, value in transformed.items()}

    def search(
        self,
        query: str,
        *,
        stock_codes: list[str],
        years: list[int],
        top_k: int = 4,
        fts_query: str | None = None,
    ) -> list[dict[str, Any]]:
        del fts_query
        candidate_k = max(top_k * 2, 2)
        corpus = self._corpus(stock_codes, years)
        bm25_rows = bm25_search(
            query,
            corpus,
            top_k=candidate_k,
            k1=self.config.bm25_k1,
            b=self.config.bm25_b,
        )
        where = {
            "$and": [
                {"stock_code": {"$in": stock_codes}},
                {"report_year": {"$in": years}},
            ]
        }
        result = self.collection.query(
            query_embeddings=[self.embedding.embed(query)],
            n_results=candidate_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        vector_scores: dict[int, float] = {}
        vector_rows: dict[int, dict[str, Any]] = {}
        for document, metadata, distance in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
        ):
            chunk_id = int(metadata["chunk_id"])
            vector_scores[chunk_id] = float(distance)
            vector_rows[chunk_id] = {**metadata, "content": document}
        bm25_scores = {int(row["chunk_id"]): float(row["bm25_score"]) for row in bm25_rows}
        candidates = {int(row["chunk_id"]): row for row in bm25_rows}
        candidates.update(vector_rows)
        normalised_vector = self._normalise(vector_scores, distance=True)
        normalised_bm25 = self._normalise(bm25_scores)
        fused: dict[int, float] = defaultdict(float)
        for chunk_id in candidates:
            fused[chunk_id] = (
                self.config.rag_vector_weight * normalised_vector.get(chunk_id, 0.0)
                + self.config.rag_bm25_weight * normalised_bm25.get(chunk_id, 0.0)
            )
        output = []
        for chunk_id in sorted(fused, key=fused.get, reverse=True)[:top_k]:
            item = dict(candidates[chunk_id])
            item.update(
                chunk_id=chunk_id,
                score=fused[chunk_id],
                fusion_score=fused[chunk_id],
                retrieval_mode="chroma_bge_m3_bm25",
                embedding_provider=self.embedding.name,
            )
            output.append(item)
        return output

    def index(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        embeddings = self.embedding.embed_many([str(row["content"]) for row in rows])
        self.collection.upsert(
            ids=[str(row["chunk_id"]) for row in rows],
            documents=[str(row["content"]) for row in rows],
            embeddings=embeddings,
            metadatas=[
                {
                    "chunk_id": int(row["chunk_id"]),
                    "stock_code": str(row["stock_code"]),
                    "company_name": str(row["company_name"]),
                    "report_year": int(row["report_year"]),
                    "source_file": str(row["source_file"]),
                    "page_number": int(row["page_number"]),
                }
                for row in rows
            ],
        )
        return len(rows)
