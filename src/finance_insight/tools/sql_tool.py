from __future__ import annotations

import sqlite3
import time
from collections.abc import Sequence
from contextlib import contextmanager
from queue import Empty, Queue
from threading import Lock
from typing import Any

from finance_insight.config import Settings, settings
from finance_insight.schemas import QueryIntent, ToolResult

BASE_QUERY = """SELECT c.stock_code,c.company_name,rp.report_year,md.metric_code,md.metric_name,
                       ff.metric_value,ff.normalized_unit,ff.source_file,ff.source_page,ff.quality_status
                FROM financial_facts ff
                JOIN companies c ON c.company_id=ff.company_id
                JOIN report_periods rp ON rp.report_period_id=ff.report_period_id
                JOIN metric_definitions md ON md.metric_id=ff.metric_id"""

RANKING_QUERY = """SELECT c.stock_code,c.company_name,rp.report_year,md.metric_code,md.metric_name,
                          ff.metric_value,ff.normalized_unit,ff.source_file,ff.source_page,ff.quality_status
                   FROM financial_facts ff
                   JOIN companies c ON c.company_id=ff.company_id
                   JOIN report_periods rp ON rp.report_period_id=ff.report_period_id
                   JOIN metric_definitions md ON md.metric_id=ff.metric_id"""


class FinancialQueryTool:
    name = "financial_query"
    description = "从结构化财务事实库安全查询年度财务指标；只接受白名单参数，不接受模型生成的自由 SQL。"

    def __init__(self, config: Settings = settings):
        self.config = config
        self.db_path = config.finance_db
        self._mysql_idle: Queue[Any] = Queue(maxsize=config.mysql_pool_size)
        self._mysql_created = 0
        self._mysql_lock = Lock()

    @staticmethod
    def _normalize_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for source in rows:
            row = dict(source)
            if row.get("metric_value") is not None:
                row["metric_value"] = float(row["metric_value"])
            normalized.append(row)
        return normalized

    def _query_sqlite(self, intent: QueryIntent) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"财务数据库不存在: {self.db_path}")
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            if intent.task_type == "ranking":
                rows = con.execute(
                    RANKING_QUERY
                    + " WHERE md.metric_code=? AND rp.report_year=? AND rp.period_code='FY'"
                    + " ORDER BY ff.metric_value DESC",
                    [intent.metrics[0], max(intent.period.years)],
                ).fetchall()
            else:
                codes = [company.stock_code for company in intent.companies]
                code_marks = ",".join("?" for _ in codes)
                metric_marks = ",".join("?" for _ in intent.metrics)
                year_marks = ",".join("?" for _ in intent.period.years)
                rows = con.execute(
                    BASE_QUERY
                    + f" WHERE c.stock_code IN ({code_marks})"
                    + f" AND md.metric_code IN ({metric_marks})"
                    + f" AND rp.report_year IN ({year_marks}) AND rp.period_code='FY'"
                    + " ORDER BY c.stock_code,md.metric_code,rp.report_year",
                    [*codes, *intent.metrics, *intent.period.years],
                ).fetchall()
        return self._normalize_rows([dict(row) for row in rows])

    def _mysql_connection(self):
        import pymysql

        return pymysql.connect(
            host=self.config.mysql_host,
            port=self.config.mysql_port,
            user=self.config.mysql_user,
            password=self.config.mysql_password,
            database=self.config.mysql_database,
            charset="utf8mb4",
            connect_timeout=self.config.mysql_connect_timeout_seconds,
            read_timeout=self.config.mysql_read_timeout_seconds,
            write_timeout=self.config.mysql_read_timeout_seconds,
            cursorclass=pymysql.cursors.DictCursor,
        )

    @staticmethod
    def _close_mysql_connection(connection: Any) -> None:
        try:
            connection.close()
        except Exception:
            pass

    @contextmanager
    def _pooled_mysql_connection(self):
        """Reuse bounded MySQL connections without hiding acquire/query failures."""
        connection = None
        reusable = False
        returned_to_pool = False
        try:
            try:
                connection = self._mysql_idle.get_nowait()
            except Empty:
                with self._mysql_lock:
                    if self._mysql_created < self.config.mysql_pool_size:
                        self._mysql_created += 1
                        create_new = True
                    else:
                        create_new = False
                if create_new:
                    try:
                        connection = self._mysql_connection()
                    except Exception:
                        with self._mysql_lock:
                            self._mysql_created -= 1
                        raise
                else:
                    try:
                        connection = self._mysql_idle.get(
                            timeout=self.config.mysql_pool_acquire_timeout_seconds
                        )
                    except Empty as exc:
                        raise TimeoutError(
                            f"MySQL 连接池已满，等待超过 {self.config.mysql_pool_acquire_timeout_seconds:.1f} 秒"
                        ) from exc
            connection.ping(reconnect=True)
            yield connection
            reusable = True
        finally:
            if connection is not None and reusable:
                try:
                    self._mysql_idle.put_nowait(connection)
                    returned_to_pool = True
                except Exception:
                    pass
            if connection is not None and not returned_to_pool:
                self._close_mysql_connection(connection)
                with self._mysql_lock:
                    self._mysql_created = max(0, self._mysql_created - 1)

    def _query_mysql(self, intent: QueryIntent) -> list[dict[str, Any]]:
        with self._pooled_mysql_connection() as connection:
            with connection.cursor() as cursor:
                if intent.task_type == "ranking":
                    cursor.execute(
                        RANKING_QUERY
                        + " WHERE md.metric_code=%s AND rp.report_year=%s AND rp.period_code='FY'"
                        + " ORDER BY ff.metric_value DESC",
                        (intent.metrics[0], max(intent.period.years)),
                    )
                else:
                    codes = [company.stock_code for company in intent.companies]
                    code_marks = ",".join("%s" for _ in codes)
                    metric_marks = ",".join("%s" for _ in intent.metrics)
                    year_marks = ",".join("%s" for _ in intent.period.years)
                    cursor.execute(
                        BASE_QUERY
                        + f" WHERE c.stock_code IN ({code_marks})"
                        + f" AND md.metric_code IN ({metric_marks})"
                        + f" AND rp.report_year IN ({year_marks}) AND rp.period_code='FY'"
                        + " ORDER BY c.stock_code,md.metric_code,rp.report_year",
                        (*codes, *intent.metrics, *intent.period.years),
                    )
                rows = cursor.fetchall()
        return self._normalize_rows(rows)

    @staticmethod
    def _with_ranks(rows: list[dict[str, Any]], intent: QueryIntent) -> list[dict[str, Any]]:
        if intent.task_type == "ranking":
            for rank, row in enumerate(rows, 1):
                row["rank"] = rank
        return rows

    def run(self, intent: QueryIntent) -> ToolResult:
        started = time.perf_counter()
        backend = self.config.finance_backend
        fallback_used = False
        fallback_reason: str | None = None
        try:
            if backend == "mysql":
                try:
                    rows = self._query_mysql(intent)
                    effective_backend = "mysql"
                except Exception as exc:
                    if not self.config.mysql_fallback_to_sqlite:
                        raise
                    fallback_reason = f"mysql_unavailable: {exc}"
                    fallback_used = True
                    try:
                        rows = self._query_sqlite(intent)
                    except Exception as fallback_exc:
                        raise RuntimeError(
                            f"MySQL 查询失败，SQLite 降级也失败；{fallback_reason}；"
                            f"sqlite_fallback_error: {fallback_exc}"
                        ) from fallback_exc
                    effective_backend = "sqlite"
            else:
                rows = self._query_sqlite(intent)
                effective_backend = "sqlite"

            rows = self._with_ranks(rows, intent)
            if not rows:
                data = {
                    "backend": effective_backend,
                    "requested_backend": backend,
                }
                if fallback_reason:
                    data["fallback_reason"] = fallback_reason
                return ToolResult(
                    tool_name=self.name,
                    status="error",
                    error="在当前 FY 2022—FY 2024 MVP 数据中没有匹配的财务事实。",
                    data=data,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    fallback_used=fallback_used,
                )
            data = {
                "records": rows,
                "record_count": len(rows),
                "scope": "FY 2022-2024 MVP",
                "backend": effective_backend,
                "requested_backend": backend,
                "connection_pool": "mysql_bounded_pool" if effective_backend == "mysql" else "not_applicable",
            }
            if fallback_reason:
                data["fallback_reason"] = fallback_reason
            return ToolResult(
                tool_name=self.name,
                status="partial" if fallback_used else "success",
                data=data,
                latency_ms=(time.perf_counter() - started) * 1000,
                fallback_used=fallback_used,
            )
        except Exception as exc:
            data = {"backend": backend, "requested_backend": backend}
            if fallback_reason:
                data["fallback_reason"] = fallback_reason
            return ToolResult(
                tool_name=self.name,
                status="error",
                error=str(exc),
                data=data,
                latency_ms=(time.perf_counter() - started) * 1000,
                fallback_used=fallback_used,
            )

    def ping(self) -> tuple[bool, str, str | None]:
        """Return availability, effective backend and an optional fallback reason."""
        if self.config.finance_backend == "mysql":
            try:
                connection = self._mysql_connection()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1 AS ok")
                        cursor.fetchone()
                finally:
                    connection.close()
                return True, "mysql", None
            except Exception as exc:
                if self.config.mysql_fallback_to_sqlite and self.db_path.exists():
                    return True, "sqlite", f"mysql_unavailable: {exc}"
                return False, "mysql", str(exc)
        return self.db_path.exists(), "sqlite", None if self.db_path.exists() else "database file missing"
