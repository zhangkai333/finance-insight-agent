import csv
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.models import DocumentSummary, IngestResponse, utc_now
from app.rag.text import chunk_text, contains_prompt_injection, hash_embedding
from app.storage import Database

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".csv"}


@dataclass
class ParsedDocument:
    text: str
    rows: list[dict[str, str]]
    warnings: list[str]


class DocumentIngestor:
    def __init__(self, database: Database):
        self.database = database

    def ingest(self, name: str, content: bytes, media_type: str) -> IngestResponse:
        extension = Path(name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {extension or 'unknown'}")
        digest = hashlib.sha256(content).hexdigest()
        self.database.initialize()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM documents WHERE content_hash=?", (digest,)
            ).fetchone()
        if existing:
            return IngestResponse(
                id=existing["id"],
                name=existing["name"],
                media_type=existing["media_type"],
                chunk_count=existing["chunk_count"],
                row_count=existing["row_count"],
                created_at=existing["created_at"],
                warnings=["相同内容已入库，本次未重复写入。"],
            )

        parsed = self._parse(extension, content)
        chunks = chunk_text(parsed.text)
        if not chunks:
            raise ValueError("No readable text found in document")
        if contains_prompt_injection(parsed.text):
            parsed.warnings.append("文档包含疑似提示注入文本；检索时将标记为不可信内容。")

        document_id = f"doc_{uuid.uuid4().hex}"
        created_at = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO documents(
                    id, name, media_type, content_hash, chunk_count, row_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    document_id,
                    name,
                    media_type,
                    digest,
                    len(chunks),
                    len(parsed.rows),
                    created_at.isoformat(),
                ),
            )
            for position, text in enumerate(chunks):
                chunk_id = f"chk_{uuid.uuid4().hex}"
                metadata = {"prompt_injection_suspected": contains_prompt_injection(text)}
                connection.execute(
                    """INSERT INTO chunks(id, document_id, position, content, embedding, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        chunk_id,
                        document_id,
                        position,
                        text,
                        json.dumps(hash_embedding(text)),
                        json.dumps(metadata),
                    ),
                )
                connection.execute(
                    "INSERT INTO chunks_fts(chunk_id, document_id, content) VALUES (?, ?, ?)",
                    (chunk_id, document_id, text),
                )
            for row_number, row in enumerate(parsed.rows, start=1):
                connection.execute(
                    "INSERT INTO financial_rows(document_id, row_number, data) VALUES (?, ?, ?)",
                    (document_id, row_number, json.dumps(row, ensure_ascii=False)),
                )

        return IngestResponse(
            id=document_id,
            name=name,
            media_type=media_type,
            chunk_count=len(chunks),
            row_count=len(parsed.rows),
            created_at=created_at,
            warnings=parsed.warnings,
        )

    def list_documents(self) -> list[DocumentSummary]:
        self.database.initialize()
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [
            DocumentSummary(
                id=row["id"],
                name=row["name"],
                media_type=row["media_type"],
                chunk_count=row["chunk_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_document(self, document_id: str) -> bool:
        self.database.initialize()
        with self.database.connect() as connection:
            chunk_ids = connection.execute(
                "SELECT id FROM chunks WHERE document_id=?", (document_id,)
            ).fetchall()
            connection.executemany(
                "DELETE FROM chunks_fts WHERE chunk_id=?", [(row["id"],) for row in chunk_ids]
            )
            cursor = connection.execute("DELETE FROM documents WHERE id=?", (document_id,))
        return cursor.rowcount > 0

    def _parse(self, extension: str, content: bytes) -> ParsedDocument:
        if extension == ".pdf":
            reader = PdfReader(io.BytesIO(content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            warnings = []
            if any(not (page.extract_text() or "").strip() for page in reader.pages):
                warnings.append("部分 PDF 页面无可提取文本，扫描件需先进行 OCR。")
            return ParsedDocument(text=text, rows=[], warnings=warnings)

        decoded = _decode(content)
        if extension != ".csv":
            return ParsedDocument(text=decoded, rows=[], warnings=[])

        sample = decoded[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
        rows = [
            {str(key).strip(): str(value or "").strip() for key, value in row.items() if key}
            for row in reader
        ]
        if not reader.fieldnames:
            raise ValueError("CSV header is missing")
        lines = [" | ".join(f"{key}: {value}" for key, value in row.items()) for row in rows]
        text = f"CSV字段: {', '.join(reader.fieldnames)}\n\n" + "\n".join(lines)
        return ParsedDocument(text=text, rows=rows, warnings=[])


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode text; use UTF-8 or GB18030 encoding")
