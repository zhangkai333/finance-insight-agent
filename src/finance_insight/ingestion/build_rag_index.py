"""Build a local, citation-preserving lexical RAG index from selected annual reports."""
from __future__ import annotations

import argparse
import csv
import sys
import json
import re
import sqlite3
from pathlib import Path

from pypdf import PdfReader


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def company_map(csv_path: Path) -> dict[str, str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        result: dict[str, str] = {}
        for row in rows:
            result.setdefault(row["stock_code"], row["company_name"])
        return result


def setup_db(connection: sqlite3.Connection, schema_path: Path) -> None:
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    connection.execute("PRAGMA foreign_keys = ON")


def index_document(
    connection: sqlite3.Connection,
    *,
    stock_code: str,
    company_name: str,
    source_path: Path,
    chunk_size: int,
    overlap: int,
) -> tuple[int, int]:
    reader = PdfReader(str(source_path))
    title = source_path.stem
    connection.execute(
        """INSERT INTO documents
           (stock_code, company_name, document_type, report_year, title, source_file, source_path, page_count, parser)
           VALUES (?, ?, 'annual_report', 2024, ?, ?, ?, ?, 'pypdf')
           ON CONFLICT(stock_code, document_type, report_year, source_file) DO UPDATE SET
             company_name = excluded.company_name, title = excluded.title,
             source_path = excluded.source_path, page_count = excluded.page_count, parser = excluded.parser""",
        (stock_code, company_name, title, source_path.name, str(source_path.resolve()), len(reader.pages)),
    )
    document_id = connection.execute(
        """SELECT document_id FROM documents
           WHERE stock_code = ? AND document_type = 'annual_report'
             AND report_year = 2024 AND source_file = ?""",
        (stock_code, source_path.name),
    ).fetchone()[0]
    old_chunk_ids = [row[0] for row in connection.execute(
        "SELECT chunk_id FROM document_chunks WHERE document_id = ?", (document_id,)
    ).fetchall()]
    if old_chunk_ids:
        connection.executemany("DELETE FROM document_chunks_fts WHERE chunk_id = ?", [(cid,) for cid in old_chunk_ids])
    connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))

    chunks_written = 0
    for page_number, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        for chunk_index, content in enumerate(split_chunks(text, chunk_size, overlap)):
            cursor = connection.execute(
                """INSERT INTO document_chunks
                   (document_id, page_number, chunk_index, content, char_count, section_hint)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (document_id, page_number, chunk_index, content, len(content), None),
            )
            chunk_id = cursor.lastrowid
            connection.execute(
                """INSERT INTO document_chunks_fts (chunk_id, document_id, content, page_number)
                   VALUES (?, ?, ?, ?)""",
                (chunk_id, document_id, content, page_number),
            )
            chunks_written += 1
    return len(reader.pages), chunks_written


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path("db/rag_schema.sql"))
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=120)
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    names = company_map(args.csv)
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    connection = sqlite3.connect(args.db)
    summary = {"documents": 0, "pages": 0, "chunks": 0, "errors": []}
    try:
        with connection:
            setup_db(connection, args.schema)
            for key, raw_path in sorted(audit["annual_documents_selected"].items()):
                source_path = Path(raw_path)
                stock_code = key if key.isdigit() else {
                    "凯莱英": "002821", "百普赛斯": "301080", "迈普医学": "301033",
                    "百诚医药": "301096", "泰格医药": "300347", "迪安诊断": "300244",
                }[key]
                try:
                    pages, chunks = index_document(
                        connection, stock_code=stock_code, company_name=names[stock_code],
                        source_path=source_path, chunk_size=args.chunk_size, overlap=args.overlap,
                    )
                    summary["documents"] += 1
                    summary["pages"] += pages
                    summary["chunks"] += chunks
                    print(f"indexed {stock_code}: pages={pages}, chunks={chunks}", flush=True)
                except Exception as exc:
                    summary["errors"].append({"stock_code": stock_code, "source_path": str(source_path), "error": str(exc)})
            summary["db_documents"] = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            summary["db_chunks"] = connection.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    finally:
        connection.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
