"""Index the SQLite demo corpus into the optional Chroma retrieval backend."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from finance_insight.config import settings  # noqa: E402
from finance_insight.rag.chroma_hybrid import ChromaHybridRetriever  # noqa: E402


def main() -> None:
    demo_data = PROJECT_ROOT / ".demo-data"
    rag_db = demo_data / "rag.sqlite3"
    if not rag_db.exists():
        raise SystemExit("Run scripts/init_demo_data.py --data-dir .demo-data first.")

    config = replace(
        settings,
        rag_db=rag_db,
        rag_backend="chroma",
        chroma_path=demo_data / "chroma",
        chroma_collection="finance_insight_demo",
    )
    retriever = ChromaHybridRetriever(config)
    indexed = retriever.index_sqlite()
    rows = retriever.search(
        "营业收入变化主要原因",
        stock_codes=["002821"],
        years=[2024],
        top_k=3,
    )
    print(
        json.dumps(
            {
                "status": "PASS" if indexed and rows else "FAIL",
                "indexed": indexed,
                "embedding_provider": retriever.embedding.name,
                "embedding_fallback": retriever.embedding_fallback,
                "hits": len(rows),
                "retrieval_mode": rows[0]["retrieval_mode"] if rows else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not indexed or not rows:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
