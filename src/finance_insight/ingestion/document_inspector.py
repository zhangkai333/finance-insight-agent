"""Inspect a small, explicit document manifest without scanning the whole dataset."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def inspect_pdf(path: Path) -> tuple[dict, list[dict]]:
    reader = PdfReader(str(path))
    pages: list[dict] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(
            {
                "page_number": page_number,
                "char_count": len(text),
                "text": text,
            }
        )
    non_empty = [page for page in pages if page["char_count"] > 0]
    return (
        {
            "file": path.name,
            "type": "pdf",
            "page_count": len(pages),
            "non_empty_pages": len(non_empty),
            "empty_pages": len(pages) - len(non_empty),
            "total_chars": sum(page["char_count"] for page in pages),
            "first_page_preview": compact(pages[0]["text"])[:200] if pages else "",
        },
        pages,
    )


def inspect_markdown(path: Path) -> tuple[dict, list[dict]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    headings = [line.strip() for line in text.splitlines() if line.lstrip().startswith("#")]
    return (
        {
            "file": path.name,
            "type": "markdown",
            "char_count": len(text),
            "line_count": len(text.splitlines()),
            "heading_count": len(headings),
            "headings_preview": headings[:10],
            "text_preview": compact(text)[:200],
        },
        [{"section": "document", "text": text}],
    )


def main() -> None:
    # Windows PowerShell may expose a GBK stdout; document names can contain Unicode.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict] = []
    pages_path = args.output_dir / "document_pages.jsonl"

    with pages_path.open("w", encoding="utf-8") as pages_file:
        for item in manifest["items"]:
            source_path = Path(item["source_path"])
            if not source_path.exists():
                raise FileNotFoundError(source_path)
            if source_path.suffix.lower() == ".pdf":
                summary, pages = inspect_pdf(source_path)
                for page in pages:
                    page_record = {
                        "company": manifest["company"],
                        "period": manifest["period"],
                        "source_file": item["file"],
                        "source_type": item["type"],
                        **{key: value for key, value in page.items() if key != "text"},
                        "text_preview": compact(page["text"])[:240],
                    }
                    pages_file.write(json.dumps(page_record, ensure_ascii=False) + "\n")
            elif source_path.suffix.lower() == ".md":
                summary, _ = inspect_markdown(source_path)
            else:
                raise ValueError(f"Unsupported file type: {source_path}")
            summaries.append({**item, **summary})

    output = {
        "company": manifest["company"],
        "stock_code": manifest["stock_code"],
        "period": manifest["period"],
        "document_count": len(summaries),
        "documents": summaries,
    }
    (args.output_dir / "document_inspection.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"PAGES_OUTPUT={pages_path.resolve()}")


if __name__ == "__main__":
    main()
