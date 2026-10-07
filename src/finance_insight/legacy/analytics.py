import json
import re
from dataclasses import dataclass

from finance_insight.legacy.storage import Database


class UnsafeQuery(ValueError):
    pass


@dataclass
class AnalyticsResult:
    text: str
    rows: list[dict[str, object]]


class SafeAnalytics:
    """A deliberately narrow analytics tool: aggregates only imported CSV rows."""

    AGGREGATE_PATTERN = re.compile(
        r"(?P<column>[\w\u4e00-\u9fff%]+?)\s*"
        r"(?P<agg>平均值|平均|均值|总和|合计|最大值|最大|最高|最小值|最小|最低)"
        r"(?:是多少|为多少|是多少？|为多少？)?"
    )
    AGGREGATE_FIRST_PATTERN = re.compile(
        r"(?P<agg>平均值|平均|均值|总和|合计|最大值|最大|最高|最小值|最小|最低)\s*"
        r"(?P<column>[\w\u4e00-\u9fff%]+)"
    )

    def __init__(self, database: Database):
        self.database = database

    def answer(
        self, question: str, document_ids: list[str] | None = None
    ) -> AnalyticsResult | None:
        match = self.AGGREGATE_PATTERN.search(question) or self.AGGREGATE_FIRST_PATTERN.search(
            question
        )
        if not match:
            return None
        rows = self._load_rows(document_ids)
        if not rows:
            return AnalyticsResult("当前没有可用于计算的 CSV 数据。", [])
        requested = match.group("column").lower()
        requested = re.sub(r"^(?:20\d{2}年|\d{4}年)", "", requested)
        values: list[float] = []
        source_column = None
        for row in rows:
            for column, value in row.items():
                normalized = str(column).strip().lower()
                if normalized == requested or requested in normalized or normalized in requested:
                    try:
                        values.append(float(str(value).replace(",", "").replace("%", "")))
                        source_column = column
                    except (TypeError, ValueError):
                        continue
        if not values or source_column is None:
            return AnalyticsResult(f"未找到可计算的数值列：{match.group('column')}。", [])
        agg = match.group("agg")
        if agg in {"平均", "均值", "平均值"}:
            result = sum(values) / len(values)
            operation = "平均值"
        elif agg in {"总和", "合计"}:
            result = sum(values)
            operation = "总和"
        elif agg in {"最大", "最高"}:
            result = max(values)
            operation = "最大值"
        else:
            result = min(values)
            operation = "最小值"
        return AnalyticsResult(
            f"基于已导入数据，{source_column}的{operation}为 {result:.2f}（共 {len(values)} 条记录）。",
            [
                {
                    "column": source_column,
                    "operation": operation,
                    "value": round(result, 2),
                    "count": len(values),
                }
            ],
        )

    def _load_rows(self, document_ids: list[str] | None) -> list[dict[str, object]]:
        self.database.initialize()
        clauses = ""
        params: list[str] = []
        if document_ids:
            clauses = f"WHERE document_id IN ({','.join('?' for _ in document_ids)})"
            params.extend(document_ids)
        with self.database.connect() as connection:
            records = connection.execute(
                f"SELECT data FROM financial_rows {clauses} ORDER BY row_number LIMIT 10000",  # noqa: S608
                params,
            ).fetchall()
        return [json.loads(record["data"]) for record in records]

