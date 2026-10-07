from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader


@dataclass(frozen=True)
class ParsedDocument:
    markdown: str
    page_count: int
    warnings: list[str]
    parser: str


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _table_to_markdown(table: list[list[Any] | None]) -> str:
    rows = [[_clean(str(cell or "")) for cell in (row or [])] for row in table]
    width = max((len(row) for row in rows), default=0)
    if not width:
        return ""
    normalised = [row + [""] * (width - len(row)) for row in rows]
    header = normalised[0]
    body = normalised[1:]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def parse_pdf(content: bytes, filename: str) -> ParsedDocument:
    warnings: list[str] = []
    pages: list[str] = []
    parser = "pdfplumber_text_tables"
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as document:
            for number, page in enumerate(document.pages, start=1):
                text = _clean(page.extract_text() or "")
                tables = [
                    markdown
                    for table in page.extract_tables()
                    if (markdown := _table_to_markdown(table))
                ]
                if not text and not tables:
                    warnings.append(f"第 {number} 页未提取到文本，扫描件可能需要 OCR")
                body = "\n\n".join(part for part in [text, *tables] if part)
                pages.append(f"## 第 {number} 页\n\n{body or '[无可提取文本]'}")
            page_count = len(document.pages)
    except ImportError:
        parser = "pypdf_text_fallback"
        warnings.append("pdfplumber 未安装，已使用 pypdf 文本提取；表格未单独解析。")
        document = PdfReader(io.BytesIO(content))
        for number, page in enumerate(document.pages, start=1):
            text = _clean(page.extract_text() or "")
            if not text:
                warnings.append(f"第 {number} 页未提取到文本，扫描件可能需要 OCR")
            pages.append(f"## 第 {number} 页\n\n{text or '[无可提取文本]'}")
        page_count = len(document.pages)
    title = Path(filename).stem
    return ParsedDocument(
        markdown=f"# {title}\n\n" + "\n\n".join(pages),
        page_count=page_count,
        warnings=warnings,
        parser=parser,
    )


def sentence_chunks(markdown: str, *, size: int = 800, overlap: int = 200) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    sections = re.split(r"(?=^## 第 \d+ 页$)", markdown, flags=re.MULTILINE)
    for section in sections:
        match = re.search(r"^## 第 (\d+) 页$", section, flags=re.MULTILINE)
        if not match:
            continue
        page = int(match.group(1))
        body = section[match.end():].strip()
        sentences = [item.strip() for item in re.split(r"(?<=[。！？.!?；;])\s*|\n+", body) if item.strip()]
        current = ""
        page_chunks: list[str] = []
        for sentence in sentences:
            if current and len(current) + len(sentence) + 1 > size:
                page_chunks.append(current.strip())
                current = (current[-overlap:] + " " + sentence).strip()
            else:
                current = (current + " " + sentence).strip()
        if current:
            page_chunks.append(current)
        for content in page_chunks:
            if len(content) >= 50:
                chunks.append({"page_number": page, "content": content})
    return chunks


def match_excel_metadata(filename: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match optional Excel-derived metadata by exact PDF stem title."""
    title = Path(filename).stem
    return next((row for row in rows if str(row.get("title", "")).strip() == title), None)


class DocumentCache:
    def __init__(self, root: Path):
        self.root = root
        self.manifest_path = root / "pdf_hashes.json"

    def prepare(
        self,
        content: bytes,
        filename: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ParsedDocument, list[dict[str, Any]], str]:
        digest = hashlib.sha256(content).hexdigest()
        metadata_fingerprint = hashlib.sha256(
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        cache_dir = self.root / "cache" / digest
        chunks_path = cache_dir / "chunks.json"
        markdown_path = cache_dir / "document.md"
        manifest: dict[str, Any] = {}
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = {}
        cached = manifest.get(digest, {})
        if (
            cached.get("metadata_fingerprint") == metadata_fingerprint
            and chunks_path.exists()
            and markdown_path.exists()
        ):
            parsed = ParsedDocument(
                markdown=markdown_path.read_text(encoding="utf-8"),
                page_count=int(cached["page_count"]),
                warnings=list(cached.get("warnings", [])),
                parser=str(cached.get("parser", "cache")),
            )
            chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
            return parsed, chunks, digest

        parsed = parse_pdf(content, filename)
        chunks = sentence_chunks(parsed.markdown)
        cache_dir.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(parsed.markdown, encoding="utf-8")
        chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest[digest] = {
            "filename": filename,
            "metadata_fingerprint": metadata_fingerprint,
            "page_count": parsed.page_count,
            "warnings": parsed.warnings,
            "parser": parsed.parser,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return parsed, chunks, digest
