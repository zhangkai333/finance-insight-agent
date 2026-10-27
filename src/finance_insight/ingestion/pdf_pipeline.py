"""Incremental PDF -> Markdown -> structured facts ingestion.

The pipeline deliberately keeps extraction and persistence in the application:
the LLM proposes JSON facts, while SQLite transactions, schema validation and
the existing whitelist metric catalog decide what can be stored.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from finance_insight.config import Settings, settings
from finance_insight.ingestion.document_pipeline import DocumentCache, parse_pdf, sentence_chunks
from finance_insight.llm import LLMClient, build_llm_client
from finance_insight.structured_output import validate_structured

METRIC_CATALOG: dict[str, dict[str, str]] = {
    "revenue": {"name": "营业收入", "unit": "万元", "value_type": "reported"},
    "net_profit_attributable": {
        "name": "归属于上市公司股东的净利润",
        "unit": "万元",
        "value_type": "reported",
    },
    "net_profit_excl_non_recurring": {
        "name": "归属于上市公司股东的扣除非经常性损益的净利润",
        "unit": "万元",
        "value_type": "reported",
    },
    "operating_cash_flow": {
        "name": "经营活动产生的现金流量净额",
        "unit": "万元",
        "value_type": "reported",
    },
    "eps": {"name": "基本每股收益", "unit": "元/股", "value_type": "reported"},
    "roe": {"name": "加权平均净资产收益率", "unit": "%", "value_type": "reported"},
    "total_assets": {"name": "总资产", "unit": "万元", "value_type": "reported"},
    "net_assets": {
        "name": "归属于上市公司股东的净资产",
        "unit": "万元",
        "value_type": "reported",
    },
}

STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["document", "facts"],
    "properties": {
        "document": {
            "type": "object",
            "required": ["stock_code", "company_name", "report_year", "document_type"],
            "properties": {
                "stock_code": {"type": "string"},
                "company_name": {"type": "string"},
                "report_year": {"type": "integer"},
                "document_type": {"type": "string"},
                "title": {"type": "string"},
            },
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "report_year",
                    "metric_code",
                    "metric_value",
                    "normalized_unit",
                    "source_page",
                ],
                "properties": {
                    "report_year": {"type": "integer"},
                    "metric_code": {"type": "string"},
                    "metric_value": {"type": "number"},
                    "normalized_unit": {"type": "string"},
                    "raw_value": {"type": ["number", "null"]},
                    "raw_unit": {"type": ["string", "null"]},
                    "source_page": {"type": "integer"},
                    "accounting_scope": {"type": "string"},
                },
            },
        },
    },
}

EXTRACTION_PROMPT = """你是上市公司财报结构化抽取器。请只依据下面的财报 Markdown，输出 JSON，不要输出 Markdown 或解释。

规则：
1. document 中提取股票代码、公司全称、报告年度和文档类型。无法确定时使用空字符串或 0，不要猜测。
2. facts 只输出能在原文中找到的年度财务事实；metric_code 只能使用给定白名单。
3. metric_value 必须是 normalized_unit 对应的数值。金额统一为“万元”，元转万元；百分比为“%”；每股收益为“元/股”。
4. source_page 是 Markdown 中的页码标记，找不到时填 0。每个事实都必须能回到原文页码。
5. 报告表格通常有多年度列，请分别输出每个 report_year，不要把同比变化率当成金额。
6. 不要输出推导指标，不要把分析观点当成事实。

允许的 metric_code：
{catalog}

JSON schema：
{schema}

财报 Markdown：
{markdown}
"""


@dataclass(frozen=True)
class PdfIngestionResult:
    status: str
    document_id: str | None
    source_hash: str
    markdown_path: str
    json_path: str
    facts_written: int
    chunks_written: int
    warnings: list[str]
    error: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def pdf_to_markdown(content: bytes, filename: str) -> tuple[str, int, list[str]]:
    parsed = parse_pdf(content, filename)
    return parsed.markdown, parsed.page_count, parsed.warnings


def _chunks(markdown: str, size: int = 800, overlap: int = 200) -> list[tuple[int, str]]:
    return [
        (int(item["page_number"]), str(item["content"]))
        for item in sentence_chunks(markdown, size=size, overlap=overlap)
    ]


def _select_extraction_markdown(markdown: str, max_chars: int) -> str:
    """Keep the full Markdown for RAG but send financially relevant pages to the LLM."""
    pages = re.split(r"(?=^## 第 \d+ 页$)", markdown, flags=re.MULTILINE)
    keywords = ("主要会计数据", "主要财务数据", "利润表", "资产负债表", "现金流量表", "营业收入")
    selected = [page for page in pages if any(keyword in page for keyword in keywords)]
    selected_text = "\n\n".join(selected)
    if len(selected_text) < 1000:
        selected_text = markdown
    if len(selected_text) <= max_chars:
        return selected_text
    return (
        selected_text[:max_chars]
        + "\n\n[后续页已保存至 Markdown/RAG，但未发送给本次结构化抽取模型]"
    )


def _normalise_output(payload: dict[str, Any], filename: str, pages: int) -> dict[str, Any]:
    document = dict(payload.get("document") or {})
    raw_stock_code = str(document.get("stock_code") or "").strip()
    if not raw_stock_code:
        raise ValueError("LLM 未能识别股票代码")
    document["stock_code"] = raw_stock_code.zfill(6)
    document["company_name"] = str(document.get("company_name") or "").strip()
    document["report_year"] = int(document.get("report_year") or 0)
    document["document_type"] = str(document.get("document_type") or "annual_report")
    document["title"] = str(document.get("title") or Path(filename).stem)
    if document["report_year"] < 1900:
        raise ValueError("LLM 未能识别有效的报告年度")

    facts: list[dict[str, Any]] = []
    for raw in payload.get("facts") or []:
        fact = dict(raw)
        code = str(fact.get("metric_code") or "")
        if code not in METRIC_CATALOG:
            continue
        year = int(fact.get("report_year") or 0)
        page = int(fact.get("source_page") or 0)
        value = fact.get("metric_value")
        if year < 1900 or value is None or page < 1 or page > pages:
            continue
        expected_unit = METRIC_CATALOG[code]["unit"]
        actual_unit = str(fact.get("normalized_unit") or "").strip()
        if actual_unit != expected_unit:
            raise ValueError(
                f"指标 {code} 的 normalized_unit 应为 {expected_unit}，实际为 {actual_unit or '空值'}"
            )
        fact.update(
            report_year=year,
            metric_code=code,
            metric_value=float(value),
            normalized_unit=expected_unit,
            source_page=page,
            raw_value=None if fact.get("raw_value") is None else float(fact["raw_value"]),
            raw_unit=fact.get("raw_unit") or METRIC_CATALOG[code]["unit"],
            accounting_scope=str(fact.get("accounting_scope") or "consolidated"),
        )
        facts.append(fact)
    if not facts:
        raise ValueError("LLM 未提取到可入库的白名单财务事实")
    return {"document": document, "facts": facts}


class PdfFinancialIngestor:
    def __init__(self, config: Settings = settings, llm: LLMClient | None = None):
        self.config = config
        self.llm = llm or build_llm_client(config)
        self.output_dir = config.pdf_ingestion_dir
        self.cache = DocumentCache(self.output_dir)

    def ingest(self, filename: str, content: bytes) -> PdfIngestionResult:
        if Path(filename).suffix.lower() != ".pdf":
            raise ValueError("该入口只接受 PDF 文件")
        digest = hashlib.sha256(content).hexdigest()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = self.output_dir / f"{digest}.md"
        json_path = self.output_dir / f"{digest}.json"
        finance_db = self.config.finance_db

        finance_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(finance_db) as con:
            con.row_factory = sqlite3.Row
            con.executescript(Path(self.config.finance_schema).read_text(encoding="utf-8"))
            row = con.execute(
                "SELECT batch_id FROM ingestion_batches WHERE source_sha256=? AND status='loaded'",
                (digest,),
            ).fetchone()
        if row and markdown_path.exists() and json_path.exists():
            return PdfIngestionResult(
                "already_ingested",
                f"pdf_{digest[:24]}",
                digest,
                str(markdown_path),
                str(json_path),
                0,
                0,
                ["相同 PDF 已入库，未重复写入。"],
            )

        parsed, prepared_chunks, cache_digest = self.cache.prepare(content, filename)
        if cache_digest != digest:
            raise RuntimeError("PDF 缓存哈希与导入哈希不一致")
        markdown = parsed.markdown
        page_count = parsed.page_count
        warnings = list(parsed.warnings)
        markdown_path.write_text(markdown, encoding="utf-8")
        messages = [
            {"role": "system", "content": "你负责财报事实抽取。严格输出符合 schema 的 JSON。"},
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(
                    catalog=json.dumps(METRIC_CATALOG, ensure_ascii=False),
                    schema=json.dumps(STRUCTURED_OUTPUT_SCHEMA, ensure_ascii=False),
                    markdown=_select_extraction_markdown(markdown, self.config.pdf_llm_max_chars),
                ),
            },
        ]
        response = self.llm.chat(messages, response_format={"type": "json_object"})
        structured = validate_structured(response.content, _LooseStructuredPayload)
        payload = _normalise_output(structured.model_dump(), filename, page_count)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        facts_written, chunks_written, document_id = self._persist(
            payload,
            filename,
            digest,
            markdown,
            page_count,
            markdown_path,
            prepared_chunks=prepared_chunks,
            parser=parsed.parser,
        )
        if self.config.rag_backend in {"chroma", "production"}:
            try:
                indexed = self._index_production_rag(filename, payload["document"])
                warnings.append(f"production RAG 已写入 {indexed} 个向量切片。")
            except Exception as exc:
                warnings.append(
                    f"production RAG 索引未完成，SQLite RAG 仍可用：{type(exc).__name__}: {exc}"
                )
        return PdfIngestionResult(
            "ingested",
            document_id,
            digest,
            str(markdown_path),
            str(json_path),
            facts_written,
            chunks_written,
            warnings,
        )

    def _persist(
        self,
        payload: dict[str, Any],
        filename: str,
        digest: str,
        markdown: str,
        page_count: int,
        markdown_path: Path,
        *,
        prepared_chunks: list[dict[str, Any]] | None = None,
        parser: str = "pypdf_markdown_llm_json",
    ) -> tuple[int, int, str]:
        document = payload["document"]
        finance_db = self.config.finance_db
        rag_db = self.config.rag_db
        finance_db.parent.mkdir(parents=True, exist_ok=True)
        rag_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(finance_db) as con:
            con.execute("PRAGMA foreign_keys=ON")
            con.executescript(Path(self.config.finance_schema).read_text(encoding="utf-8"))
            con.execute(
                "INSERT OR IGNORE INTO companies(stock_code, company_name) VALUES (?, ?)",
                (document["stock_code"], document["company_name"]),
            )
            company_id = con.execute(
                "SELECT company_id FROM companies WHERE stock_code=?", (document["stock_code"],)
            ).fetchone()[0]
            metric_ids: dict[str, int] = {}
            for code, meta in METRIC_CATALOG.items():
                con.execute(
                    "INSERT OR IGNORE INTO metric_definitions(metric_code, metric_name, category, default_unit, value_type) VALUES (?, ?, ?, ?, ?)",
                    (code, meta["name"], "财务指标", meta["unit"], meta["value_type"]),
                )
                metric_ids[code] = con.execute(
                    "SELECT metric_id FROM metric_definitions WHERE metric_code=?", (code,)
                ).fetchone()[0]
            for fact in payload["facts"]:
                con.execute(
                    "INSERT OR IGNORE INTO report_periods(period_code, report_year, report_quarter, period_label) VALUES ('FY', ?, 4, ?)",
                    (fact["report_year"], f"FY{fact['report_year']}"),
                )
                period_id = con.execute(
                    "SELECT report_period_id FROM report_periods WHERE period_code='FY' AND report_year=? AND report_quarter=4",
                    (fact["report_year"],),
                ).fetchone()[0]
                con.execute(
                    """INSERT INTO financial_facts(company_id, report_period_id, metric_id, metric_value, normalized_unit, raw_value, raw_unit, accounting_scope, value_type, source_file, source_page, extraction_method, quality_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'llm_json_from_pdf', 'auto_ingested')
                    ON CONFLICT(company_id, report_period_id, metric_id) DO UPDATE SET metric_value=excluded.metric_value, normalized_unit=excluded.normalized_unit, raw_value=excluded.raw_value, raw_unit=excluded.raw_unit, source_file=excluded.source_file, source_page=excluded.source_page, extraction_method=excluded.extraction_method, quality_status=excluded.quality_status""",
                    (
                        company_id,
                        period_id,
                        metric_ids[fact["metric_code"]],
                        fact["metric_value"],
                        fact["normalized_unit"],
                        fact["raw_value"],
                        fact["raw_unit"],
                        fact["accounting_scope"],
                        METRIC_CATALOG[fact["metric_code"]]["value_type"],
                        filename,
                        fact["source_page"],
                    ),
                )
            batch_id = f"pdf_{digest[:24]}"
            con.execute(
                "INSERT OR REPLACE INTO ingestion_batches(batch_id, source_path, source_sha256, row_count, status, error_message) VALUES (?, ?, ?, ?, 'loaded', NULL)",
                (batch_id, str(markdown_path), digest, len(payload["facts"])),
            )
            document_id = f"pdf_{digest[:24]}"

        with sqlite3.connect(rag_db) as con:
            con.execute("PRAGMA foreign_keys=ON")
            con.executescript(Path(self.config.rag_schema).read_text(encoding="utf-8"))
            con.execute(
                "INSERT OR IGNORE INTO documents(stock_code, company_name, document_type, report_year, title, source_file, source_path, page_count, parser) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document["stock_code"],
                    document["company_name"],
                    document["document_type"],
                    document["report_year"],
                    document["title"],
                    filename,
                    str(markdown_path),
                    page_count,
                    parser,
                ),
            )
            rag_document_id = con.execute(
                "SELECT document_id FROM documents WHERE stock_code=? AND document_type=? AND report_year=? AND source_file=?",
                (
                    document["stock_code"],
                    document["document_type"],
                    document["report_year"],
                    filename,
                ),
            ).fetchone()[0]
            old = [
                row[0]
                for row in con.execute(
                    "SELECT chunk_id FROM document_chunks WHERE document_id=?", (rag_document_id,)
                ).fetchall()
            ]
            if old:
                con.executemany(
                    "DELETE FROM document_chunks_fts WHERE chunk_id=?", [(item,) for item in old]
                )
            con.execute("DELETE FROM document_chunks WHERE document_id=?", (rag_document_id,))
            chunks = (
                [(int(item["page_number"]), str(item["content"])) for item in prepared_chunks]
                if prepared_chunks is not None
                else _chunks(markdown)
            )
            for index, (page, content) in enumerate(chunks):
                cursor = con.execute(
                    "INSERT INTO document_chunks(document_id, page_number, chunk_index, content, char_count, section_hint) VALUES (?, ?, ?, ?, ?, ?)",
                    (rag_document_id, page, index, content, len(content), "pdf_markdown"),
                )
                con.execute(
                    "INSERT INTO document_chunks_fts(chunk_id, document_id, content, page_number) VALUES (?, ?, ?, ?)",
                    (cursor.lastrowid, rag_document_id, content, page),
                )
        return len(payload["facts"]), len(chunks), str(document_id)

    def _index_production_rag(self, filename: str, document: dict[str, Any]) -> int:
        from finance_insight.rag.chroma_hybrid import ChromaHybridRetriever

        with sqlite3.connect(self.config.rag_db) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT d.stock_code,d.company_name,d.report_year,d.source_file,
                          c.page_number,c.chunk_id,c.content
                   FROM document_chunks c JOIN documents d ON d.document_id=c.document_id
                   WHERE d.stock_code=? AND d.report_year=? AND d.source_file=?""",
                (document["stock_code"], document["report_year"], filename),
            ).fetchall()
        return ChromaHybridRetriever(self.config).index([dict(row) for row in rows])


class _LooseStructuredPayload(BaseModel):
    document: dict[str, Any]
    facts: list[dict[str, Any]]
