from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from finance_insight.schemas import ToolResult


class FinancialAnalysisTool:
    name = "financial_analysis"
    description = "Python 执行同比、CAGR、趋势与异常检测。"

    def run(self, records: list[dict[str, Any]], *, detect_anomalies: bool = True) -> ToolResult:
        started = time.perf_counter()
        try:
            groups = defaultdict(list)
            for row in records:
                groups[(row["stock_code"], row["metric_code"])].append(row)
            series = []
            anomalies = []
            for (code, metric), rows in groups.items():
                rows = sorted(rows, key=lambda x: x["report_year"])
                points = []
                for i, row in enumerate(rows):
                    point = {
                        "year": row["report_year"],
                        "value": float(row["metric_value"]),
                        "unit": row["normalized_unit"],
                    }
                    if i:
                        previous_year = int(rows[i - 1]["report_year"])
                        year_gap = int(row["report_year"]) - previous_year
                        prev = float(rows[i - 1]["metric_value"])
                        yoy = (
                            (point["value"] - prev) / abs(prev) * 100
                            if year_gap == 1 and prev != 0
                            else None
                        )
                        point["yoy_pct"] = None if yoy is None else round(yoy, 2)
                        if detect_anomalies and yoy is not None and abs(yoy) >= 20:
                            anomalies.append(
                                {
                                    "stock_code": code,
                                    "company_name": row["company_name"],
                                    "metric_code": metric,
                                    "year": row["report_year"],
                                    "type": "large_yoy_change",
                                    "change_pct": round(yoy, 2),
                                    "message": f"{metric} 同比变化 {yoy:.2f}%",
                                }
                            )
                        if (
                            detect_anomalies
                            and year_gap == 1
                            and metric == "roe"
                            and abs(point["value"] - prev) >= 5
                        ):
                            anomalies.append(
                                {
                                    "stock_code": code,
                                    "company_name": row["company_name"],
                                    "metric_code": metric,
                                    "year": row["report_year"],
                                    "type": "roe_point_change",
                                    "change_pct": round(point["value"] - prev, 2),
                                    "message": f"ROE 变化 {point['value'] - prev:.2f} 个百分点",
                                }
                            )
                    points.append(point)
                cagr = None
                years_elapsed = (
                    int(points[-1]["year"]) - int(points[0]["year"]) if len(points) >= 2 else 0
                )
                if years_elapsed > 0 and points[0]["value"] > 0 and points[-1]["value"] > 0:
                    cagr = (
                        (points[-1]["value"] / points[0]["value"]) ** (1 / years_elapsed) - 1
                    ) * 100
                series.append(
                    {
                        "stock_code": code,
                        "company_name": rows[0]["company_name"],
                        "metric_code": metric,
                        "metric_name": rows[0]["metric_name"],
                        "points": points,
                        "cagr_pct": None if cagr is None else round(cagr, 2),
                    }
                )
            return ToolResult(
                tool_name=self.name,
                status="success",
                data={
                    "series": series,
                    "anomalies": anomalies,
                    "anomaly_count": len(anomalies),
                    "rules": {"yoy_pct": 20, "roe_point_change": 5},
                },
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                status="error",
                error=str(exc),
                latency_ms=(time.perf_counter() - started) * 1000,
            )
