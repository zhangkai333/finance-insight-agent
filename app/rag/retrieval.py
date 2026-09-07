import json
from dataclasses import dataclass

from app.rag.text import cosine_similarity, hash_embedding, tokenize
from app.storage import Database


@dataclass
class RetrievedChunk:
    id: str
    document_id: str
    document_name: str
    content: str
    score: float
    lexical_score: float
    vector_score: float
    injection_suspected: bool


class HybridRetriever:
    def __init__(self, database: Database):
        self.database = database

    def search(
        self, query: str, *, document_ids: list[str] | None = None, top_k: int = 5
    ) -> list[RetrievedChunk]:
        self.database.initialize()
        candidate_limit = max(top_k * 5, 20)
        lexical = self._lexical_search(query, document_ids, candidate_limit)
        candidates = self._all_candidates(document_ids, limit=1000)
        query_embedding = hash_embedding(query)
        vector = sorted(
            (
                (
                    row["id"],
                    max(0.0, cosine_similarity(query_embedding, json.loads(row["embedding"]))),
                )
                for row in candidates
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:candidate_limit]

        lexical_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(lexical, start=1)}
        vector_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(vector, start=1)}
        lexical_raw = dict(lexical)
        vector_raw = dict(vector)
        row_by_id = {row["id"]: row for row in candidates}
        ids = set(lexical_ranks) | set(vector_ranks)
        query_tokens = set(tokenize(query))
        ranked: list[RetrievedChunk] = []

        for chunk_id in ids:
            row = row_by_id.get(chunk_id)
            if row is None:
                continue
            rrf = 0.0
            if chunk_id in lexical_ranks:
                rrf += 0.55 / (60 + lexical_ranks[chunk_id])
            if chunk_id in vector_ranks:
                rrf += 0.45 / (60 + vector_ranks[chunk_id])
            content_tokens = set(tokenize(row["content"]))
            coverage = len(query_tokens & content_tokens) / max(1, len(query_tokens))
            rerank = 0.7 * (rrf * 61) + 0.3 * coverage
            metadata = Database.parse_json(row["metadata"], {})
            ranked.append(
                RetrievedChunk(
                    id=chunk_id,
                    document_id=row["document_id"],
                    document_name=row["name"],
                    content=row["content"],
                    score=min(1.0, max(0.0, rerank)),
                    lexical_score=lexical_raw.get(chunk_id, 0.0),
                    vector_score=vector_raw.get(chunk_id, 0.0),
                    injection_suspected=bool(metadata.get("prompt_injection_suspected")),
                )
            )
        return sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k]

    def _lexical_search(
        self, query: str, document_ids: list[str] | None, limit: int
    ) -> list[tuple[str, float]]:
        tokens = [token.replace('"', "") for token in tokenize(query) if len(token) > 1]
        if not tokens:
            return []
        match_query = " OR ".join(f'"{token}"' for token in tokens[:20])
        filters = ""
        parameters: list[object] = [match_query]
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            filters = f" AND document_id IN ({placeholders})"
            parameters.extend(document_ids)
        parameters.append(limit)
        try:
            with self.database.connect() as connection:
                rows = connection.execute(
                    f"""SELECT chunk_id, bm25(chunks_fts) AS rank FROM chunks_fts
                    WHERE chunks_fts MATCH ? {filters} ORDER BY rank LIMIT ?""",  # noqa: S608
                    parameters,
                ).fetchall()
        except Exception:
            return []
        return [(row["chunk_id"], 1 / (1 + abs(row["rank"]))) for row in rows]

    def _all_candidates(self, document_ids: list[str] | None, limit: int):
        where = ""
        parameters: list[object] = []
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            where = f"WHERE c.document_id IN ({placeholders})"
            parameters.extend(document_ids)
        parameters.append(limit)
        with self.database.connect() as connection:
            return connection.execute(
                f"""SELECT c.*, d.name FROM chunks c JOIN documents d ON d.id=c.document_id
                {where} ORDER BY d.created_at DESC, c.position LIMIT ?""",  # noqa: S608
                parameters,
            ).fetchall()
