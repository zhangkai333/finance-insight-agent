from __future__ import annotations

from typing import Any

from finance_insight.schemas import QueryIntent, ValidationReport
from finance_insight.tools.rag_tool import (
    METRIC_EVIDENCE_TERMS,
    has_cause_evidence,
    has_metric_evidence,
)


def validate_evidence(
    intent: QueryIntent | None,
    financial_data: list[dict[str, Any]],
    calculations: dict[str, Any],
    citations: list[dict[str, Any]],
    *,
    errors: list[str] | None = None,
) -> ValidationReport:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = list(errors or [])
    if intent is None:
        return ValidationReport(
            status="warning",
            checks=[{"name": "clarification", "passed": True}],
            warnings=["信息不足，已进入澄清分支，未执行数据工具。"],
        )

    expected = {
        (company.stock_code, year, metric)
        for company in intent.companies
        for year in intent.period.years
        for metric in intent.metrics
    }
    actual = {
        (row.get("stock_code"), row.get("report_year"), row.get("metric_code"))
        for row in financial_data
    }
    coverage = len(expected & actual) / len(expected) if expected else 0.0
    checks.append(
        {"name": "fact_coverage", "passed": coverage >= 1.0, "coverage": round(coverage, 3)}
    )
    if expected and coverage < 1.0:
        warnings.append(f"结构化事实覆盖率不足：{coverage:.0%}")

    numeric_ok = all(isinstance(row.get("metric_value"), (int, float)) for row in financial_data)
    checks.append({"name": "numeric_facts", "passed": numeric_ok})
    if not numeric_ok:
        warnings.append("存在无法确认数值类型的财务事实")

    series = calculations.get("series", []) if calculations else []
    calc_ok = all(
        all(point.get("value") is not None for point in item.get("points", [])) for item in series
    )
    checks.append({"name": "calculation_trace", "passed": calc_ok, "series_count": len(series)})
    if (intent.needs_calculation or intent.needs_anomaly_detection) and not series:
        warnings.append("用户要求计算或异常分析，但没有生成可复核序列")

    covered_metrics = {
        metric
        for citation in citations
        for metric in intent.metrics
        if citation.get("matched_metric") == metric
        and has_metric_evidence(citation.get("snippet", ""), METRIC_EVIDENCE_TERMS.get(metric, ()))
    }
    missing_metrics = sorted(set(intent.metrics) - covered_metrics) if intent.needs_rag else []
    citation_ok = not missing_metrics
    checks.append(
        {
            "name": "citation_coverage",
            "passed": citation_ok,
            "citation_count": len(citations),
            "covered_metrics": sorted(covered_metrics),
            "missing_metrics": missing_metrics,
        }
    )
    if intent.needs_rag and not citations:
        warnings.append("归因/解释问题没有返回原文引用")
    elif missing_metrics:
        warnings.append(f"部分指标缺少相关原文引用：{', '.join(missing_metrics)}")

    needs_cause = any(word in intent.question for word in ("原因", "解释", "为什么", "归因"))
    cause_metrics = {
        citation.get("matched_metric")
        for citation in citations
        if citation.get("matched_metric") in covered_metrics
        and has_cause_evidence(
            citation.get("snippet", ""),
            METRIC_EVIDENCE_TERMS.get(citation.get("matched_metric"), ()),
        )
    }
    missing_cause = sorted(set(intent.metrics) - cause_metrics) if needs_cause else []
    if needs_cause:
        checks.append(
            {
                "name": "cause_evidence",
                "passed": not missing_cause,
                "covered_metrics": sorted(cause_metrics),
                "missing_metrics": missing_cause,
            }
        )
        if missing_cause:
            warnings.append(f"部分指标缺少明确的原因原文证据：{', '.join(missing_cause)}")

    status = (
        "failed"
        if any(not check["passed"] for check in checks if check["name"] == "numeric_facts")
        else "warning"
        if warnings
        else "passed"
    )
    return ValidationReport(status=status, checks=checks, warnings=warnings)
