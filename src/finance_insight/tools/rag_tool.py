from __future__ import annotations

import re
import sqlite3
import time

from finance_insight.config import Settings, settings
from finance_insight.rag.hybrid import HybridRetriever
from finance_insight.rag.query_rewrite import rewrite_financial_query
from finance_insight.rag.rerank import LexicalMetadataReranker, Reranker, evidence_sufficiency
from finance_insight.schemas import QueryIntent, ToolResult

METRIC_EVIDENCE_TERMS = {
    "revenue": ("营业收入", "营业总收入", "营收"),
    "net_profit_attributable": ("归属于上市公司股东的净利润", "归母净利润"),
    "net_profit_excl_non_recurring": ("扣除非经常性损益", "扣非净利润"),
    "roe": ("净资产收益率",),
    "operating_cash_flow": ("经营活动产生的现金流量", "经营现金流"),
}
CAUSE_TERMS = (
    "主要系",
    "主要原因",
    "原因如下",
    "原因在于",
    "所致",
    "导致",
    "等因素",
)
CHANGE_TERMS = ("下降", "减少", "增长", "增加", "承压", "挤压", "降低", "提升", "变动")


def normalize_evidence_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def has_metric_evidence(text: str, terms: tuple[str, ...]) -> bool:
    normalized = normalize_evidence_text(text)
    return any(normalize_evidence_text(term) in normalized for term in terms)


def has_cause_evidence(text: str, terms: tuple[str, ...] = ()) -> bool:
    metric_terms = terms or tuple(
        term for aliases in METRIC_EVIDENCE_TERMS.values() for term in aliases
    ) + ("净利润", "利润空间", "毛利率")
    for sentence in re.split(r"[。！？；]", normalize_evidence_text(text)):
        if not has_metric_evidence(sentence, metric_terms):
            continue
        if not any(term in sentence for term in CHANGE_TERMS):
            continue
        if any(term in sentence for term in CAUSE_TERMS):
            return True
        if "由于" in sentence or re.search(r"受.{1,40}影响", sentence):
            return True
    return False


def _metric_excerpt(content: str, terms: tuple[str, ...], limit: int = 480) -> str:
    text = " ".join(content.split())
    if not terms:
        return text[:limit]

    sentences = [part.strip() for part in re.split(r"(?<=[。！？；])", text) if part.strip()]
    relevant: list[str] = []
    in_cause_list = False
    for sentence in sentences:
        metric_match = has_metric_evidence(sentence, terms)
        # PDF paragraphs can separate a metric introduction from its numbered causes.
        numbered_cause = bool(re.match(r"[（(]?\d+[）)、.]", sentence))
        if metric_match or (in_cause_list and numbered_cause):
            relevant.append(sentence)
        elif in_cause_list and not numbered_cause:
            in_cause_list = False
        if metric_match and has_cause_evidence(sentence, terms):
            in_cause_list = True
    excerpt = " ".join(relevant) if relevant else text
    if len(excerpt) <= limit:
        return excerpt
    cause_positions = [
        match.start() for match in re.finditer(r"主要系|主要原因|原因如下|原因在于", excerpt)
    ]
    start = max(0, min(cause_positions) - 120) if cause_positions else 0
    return excerpt[start : start + limit]


class AnnualReportSearchTool:
    name = "annual_report_search"
    description = "检索年报原文，返回文件名、页码与内容切片。"

    def __init__(
        self,
        config: Settings = settings,
        reranker: Reranker | None = None,
    ):
        self.config = config
        self.db_path = config.rag_db
        self.requested_backend = config.rag_backend
        self.effective_backend = "sqlite"
        self.backend_initialization_error: str | None = None
        self.retriever = HybridRetriever(self.db_path)
        if config.rag_backend in {"chroma", "production"}:
            try:
                from finance_insight.rag.chroma_hybrid import ChromaHybridRetriever

                self.retriever = ChromaHybridRetriever(config)
                self.effective_backend = "chroma"
            except Exception as exc:
                self.backend_initialization_error = (
                    f"production_rag_unavailable: {type(exc).__name__}: {exc}"
                )
        self.reranker = reranker or LexicalMetadataReranker(config.rerank_max_chars)

    def _fts_search(
        self,
        fts_query: str,
        terms: list[str],
        *,
        stock_codes: list[str],
        years: list[int],
        top_k: int,
    ) -> list[dict]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            code_marks = ",".join("?" for _ in stock_codes)
            year_marks = ",".join("?" for _ in years)
            sql = f"""SELECT d.stock_code,d.company_name,d.report_year,d.source_file,
                             c.page_number,c.chunk_id,c.content,
                             bm25(document_chunks_fts) AS score
                      FROM document_chunks_fts f
                      JOIN document_chunks c ON c.chunk_id=f.chunk_id
                      JOIN documents d ON d.document_id=c.document_id
                      WHERE document_chunks_fts MATCH ?
                        AND d.stock_code IN ({code_marks})
                        AND d.report_year IN ({year_marks})
                      ORDER BY score LIMIT ?"""
            try:
                rows = [
                    dict(row)
                    for row in con.execute(sql, [fts_query, *stock_codes, *years, top_k]).fetchall()
                ]
                for row in rows:
                    row["retrieval_mode"] = "fts5"
                return rows
            except sqlite3.OperationalError:
                # FTS 查询语法或扩展不可用时，按改写词构建参数化 LIKE fallback。
                like_clause = " OR ".join("c.content LIKE ?" for _ in terms)
                sql = f"""SELECT d.stock_code,d.company_name,d.report_year,d.source_file,
                                 c.page_number,c.chunk_id,c.content,NULL AS score
                          FROM document_chunks c
                          JOIN documents d ON d.document_id=c.document_id
                          WHERE ({like_clause})
                            AND d.stock_code IN ({code_marks})
                            AND d.report_year IN ({year_marks})
                          LIMIT ?"""
                rows = [
                    dict(row)
                    for row in con.execute(
                        sql, [*[f"%{term}%" for term in terms], *stock_codes, *years, top_k]
                    ).fetchall()
                ]
                for row in rows:
                    row["retrieval_mode"] = "like_fallback"
                return rows
        finally:
            con.close()

    def run(
        self,
        intent: QueryIntent,
        *,
        query: str | None = None,
        top_k: int = 4,
    ) -> ToolResult:
        started = time.perf_counter()
        search_query = query or "主要原因"
        fallback_used = False
        fallback_reason = self.backend_initialization_error
        try:
            stock_codes = [company.stock_code for company in intent.companies]
            # MVP 年报库当前是一家公司一份最新年报，原因解释优先检索问题范围内最新年份。
            years = [max(intent.period.years)]
            rows: list[dict] = []
            attempts: list[dict] = []
            evidence_score = 0.0
            sufficient = False
            final_rewrite = rewrite_financial_query(search_query)
            needs_cause = any(
                word in intent.question for word in ("原因", "解释", "为什么", "归因")
            )
            vector_available = self.retriever.available()
            effective_backend = self.effective_backend
            if not vector_available:
                fallback_used = True
                fallback_reason = fallback_reason or "vector_index_unavailable"
                if self.requested_backend in {"chroma", "production"}:
                    effective_backend = "sqlite"

            for attempt_number in range(1, self.config.rag_max_retrieval_rounds + 1):
                rewritten = rewrite_financial_query(search_query, broaden=attempt_number == 2)
                final_rewrite = rewritten
                candidates: list[dict] = []
                if vector_available:
                    try:
                        candidates = self.retriever.search(
                            search_query,
                            fts_query=rewritten.fts_expression,
                            stock_codes=stock_codes,
                            years=years,
                            top_k=top_k * 4,
                        )
                    except Exception as exc:
                        fallback_used = True
                        fallback_reason = f"hybrid_search_failed: {exc}"
                        effective_backend = "sqlite"

                if not candidates:
                    candidates = self._fts_search(
                        rewritten.fts_expression,
                        terms=rewritten.terms,
                        stock_codes=stock_codes,
                        years=years,
                        top_k=top_k * 4,
                    )
                if len(intent.metrics) > 1 or needs_cause:
                    for metric in intent.metrics:
                        terms = METRIC_EVIDENCE_TERMS.get(metric, ())
                        if not terms:
                            continue
                        candidates.extend(
                            self._fts_search(
                                " OR ".join(f'"{term}"' for term in terms),
                                terms=list(terms),
                                stock_codes=stock_codes,
                                years=years,
                                top_k=top_k * 4,
                            )
                        )
                # Preserve richer hybrid records when lexical supplementation returns
                # the same chunk with a simpler fallback trace.
                by_id: dict[int, dict] = {}
                for row in [*rows, *candidates]:
                    by_id.setdefault(row["chunk_id"], row)
                ranked = self.reranker.rerank(
                    list(by_id.values()),
                    terms=rewritten.terms,
                    stock_codes=stock_codes,
                    years=years,
                    top_k=len(by_id),
                )
                rows = []
                for metric in intent.metrics:
                    terms = METRIC_EVIDENCE_TERMS.get(metric, ())
                    for row in ranked:
                        excerpt = _metric_excerpt(str(row.get("content", "")), terms)
                        if terms and not has_metric_evidence(excerpt, terms):
                            continue
                        if needs_cause and not has_cause_evidence(excerpt, terms):
                            continue
                        rows.append({**row, "excerpt": excerpt, "matched_metric": metric})
                        break
                if len(rows) < top_k:
                    seen = {(row["chunk_id"], row["matched_metric"]) for row in rows}
                    covered_metrics = {row["matched_metric"] for row in rows}
                    for row in ranked:
                        for metric in intent.metrics:
                            if metric not in covered_metrics:
                                continue
                            if (row["chunk_id"], metric) in seen:
                                continue
                            terms = METRIC_EVIDENCE_TERMS.get(metric, ())
                            excerpt = _metric_excerpt(str(row.get("content", "")), terms)
                            if terms and not has_metric_evidence(excerpt, terms):
                                continue
                            if needs_cause and not has_cause_evidence(excerpt, terms):
                                continue
                            rows.append({**row, "excerpt": excerpt, "matched_metric": metric})
                            seen.add((row["chunk_id"], metric))
                            if len(rows) >= top_k:
                                break
                        if len(rows) >= top_k:
                            break
                evidence_score, sufficient = evidence_sufficiency(rows, rewritten.terms)
                attempts.append(
                    {
                        "round": attempt_number,
                        "terms": rewritten.terms,
                        "candidate_count": len(candidates),
                        "evidence_score": evidence_score,
                        "sufficient": sufficient,
                    }
                )
                if sufficient and (
                    not intent.metrics
                    or {row["matched_metric"] for row in rows} >= set(intent.metrics)
                ):
                    break

            citations = [
                {
                    key: row[key]
                    for key in (
                        "stock_code",
                        "company_name",
                        "report_year",
                        "source_file",
                        "page_number",
                        "chunk_id",
                    )
                }
                for row in rows
            ]
            for citation, row in zip(citations, rows, strict=True):
                citation["snippet"] = row["excerpt"]
                citation["matched_metric"] = row["matched_metric"]
                citation["retrieval_mode"] = row.get("retrieval_mode", "unknown")
            retrieval_mode = rows[0].get("retrieval_mode") if rows else "none"
            data = {
                "query": search_query,
                "requested_rag_backend": self.requested_backend,
                "effective_rag_backend": effective_backend,
                "rewritten_terms": final_rewrite.terms,
                "fts_expression": final_rewrite.fts_expression,
                "chunks": rows,
                "retrieval_mode": retrieval_mode,
                "reranker": self.reranker.name,
                "retrieval_attempts": len(attempts),
                "candidate_count": sum(item["candidate_count"] for item in attempts),
                "evidence_score": evidence_score,
                "evidence_sufficient": sufficient,
                "cause_evidence_sufficient": not needs_cause
                or all(
                    any(
                        row["matched_metric"] == metric
                        and has_cause_evidence(
                            row["excerpt"], METRIC_EVIDENCE_TERMS.get(metric, ())
                        )
                        for row in rows
                    )
                    for metric in intent.metrics
                ),
                "attempt_trace": attempts,
            }
            if rows and rows[0].get("embedding_provider"):
                data["embedding_provider"] = rows[0]["embedding_provider"]
            if fallback_reason:
                data["fallback_reason"] = fallback_reason

            return ToolResult(
                tool_name=self.name,
                status=(
                    "partial"
                    if not rows or (needs_cause and not data["cause_evidence_sufficient"])
                    else "success"
                ),
                data=data,
                citations=citations,
                latency_ms=(time.perf_counter() - started) * 1000,
                fallback_used=fallback_used,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                status="error",
                error=str(exc),
                latency_ms=(time.perf_counter() - started) * 1000,
                fallback_used=fallback_used,
            )
