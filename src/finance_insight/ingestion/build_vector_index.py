from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import sqlite_vec

from finance_insight.rag.embeddings import HashingEmbedding


def build(db_path: Path, dimension: int = 256) -> dict:
    embedding = HashingEmbedding(dimension)
    con = sqlite3.connect(db_path)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    try:
        with con:
            con.execute("DROP TABLE IF EXISTS chunk_vectors")
            con.execute(
                f"CREATE VIRTUAL TABLE chunk_vectors USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[{dimension}])"
            )
            rows = con.execute(
                "SELECT chunk_id, content FROM document_chunks ORDER BY chunk_id"
            ).fetchall()
            con.executemany(
                "INSERT INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?)",
                [(chunk_id, embedding.serialize(content)) for chunk_id, content in rows],
            )
        count = con.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
    finally:
        con.close()
    return {"status": "PASS", "vectors": count, "dimension": dimension, "provider": embedding.name}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/rag.sqlite3"))
    parser.add_argument("--dimension", type=int, default=256)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/mvp_dataset/vector_index_validation.json"),
    )
    args = parser.parse_args()
    result = build(args.db, args.dimension)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
