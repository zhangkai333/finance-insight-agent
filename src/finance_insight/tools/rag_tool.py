from __future__ import annotations

import sqlite3
import time

from finance_insight.config import Settings, settings
from finance_insight.rag.hybrid import HybridRetriever
from finance_insight.schemas import QueryIntent, ToolResult


class AnnualReportSearchTool:
    name = "annual_report_search"
    description = "检索年报原文，返回文件名、页码与内容切片。"

    def __init__(self, config: Settings = settings):
        self.db_path = config.rag_db
        self.retriever = HybridRetriever(self.db_path)

    def _fts_search(
        self,
        query: str,
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
                    for row in con.execute(
                        sql, [query, *stock_codes, *years, top_k]
                    ).fetchall()
                ]
                for row in rows:
                    row["retrieval_mode"] = "fts5"
                return rows
            except sqlite3.OperationalError:
                # FTS 查询语法或扩展不可用时，保留最小 LIKE fallback。
                sql = f"""SELECT d.stock_code,d.company_name,d.report_year,d.source_file,
                                 c.page_number,c.chunk_id,c.content,NULL AS score
                          FROM document_chunks c
                          JOIN documents d ON d.document_id=c.document_id
                          WHERE c.content LIKE ?
                            AND d.stock_code IN ({code_marks})
                            AND d.report_year IN ({year_marks})
                          LIMIT ?"""
                rows = [
                    dict(row)
                    for row in con.execute(
                        sql, [f"%{query}%", *stock_codes, *years, top_k]
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
        fallback_reason: str | None = None
        try:
            stock_codes = [company.stock_code for company in intent.companies]
            # MVP 年报库当前是一家公司一份最新年报，原因解释优先检索问题范围内最新年份。
            years = [max(intent.period.years)]
            rows: list[dict] = []

            try:
                if self.retriever.available():
                    rows = self.retriever.search(
                        search_query,
                        stock_codes=stock_codes,
                        years=years,
                        top_k=top_k,
                    )
                else:
                    fallback_used = True
                    fallback_reason = "vector_index_unavailable"
            except Exception as exc:
                # 向量扩展、索引或检索异常不能中断 Agent 主链路。
                fallback_used = True
                fallback_reason = f"hybrid_search_failed: {exc}"

            if not rows:
                fallback_used = True
                fallback_reason = fallback_reason or "hybrid_search_empty"
                rows = self._fts_search(
                    search_query,
                    stock_codes=stock_codes,
                    years=years,
                    top_k=top_k,
                )

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
            retrieval_mode = rows[0].get("retrieval_mode") if rows else "none"
            data = {
                "query": search_query,
                "chunks": rows,
                "retrieval_mode": retrieval_mode,
            }
            if rows and rows[0].get("embedding_provider"):
                data["embedding_provider"] = rows[0]["embedding_provider"]
            if fallback_reason:
                data["fallback_reason"] = fallback_reason

            return ToolResult(
                tool_name=self.name,
                status="success" if rows else "partial",
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
