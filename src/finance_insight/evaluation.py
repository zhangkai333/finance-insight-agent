from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

from finance_insight.agent import FinanceInsightAgent
from finance_insight.tools import FinancialQueryTool


def percentile(values: list[float], quantile: float) -> float:
    """Return a linear-interpolated percentile without an extra dependency."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def run(dataset_path: Path, output_path: Path, *, use_llm: bool = False) -> dict:
    cases = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("评测集必须是非空 JSON 数组")

    agent = FinanceInsightAgent()
    rows = []
    for case in cases:
        started = time.perf_counter()
        result = agent.run(case["question"], use_llm=use_llm)
        latency = (time.perf_counter() - started) * 1000
        actual_tools = [event["tool_name"] for event in result.tool_events]
        company_ok = case.get("expected_company") is None or (
            result.intent is not None
            and bool(result.intent.companies)
            and result.intent.companies[0].stock_code == case["expected_company"]
        )
        metric_ok = result.intent is not None and set(result.intent.metrics) == set(
            case["expected_metrics"]
        )
        if not case.get("expected_metrics"):
            metric_ok = result.intent is None or not result.intent.metrics
        tool_ok = actual_tools == case["expected_tools"]
        citation_ok = len(result.citations) >= case.get("min_citations", 0)
        chart_ok = len(result.charts) >= case.get("min_charts", 0)
        status_ok = result.status == case.get("expected_status", "success")
        strategy_ok = case.get("expected_plan_strategy") is None or (
            result.task_plan is not None
            and result.task_plan.strategy == case["expected_plan_strategy"]
        )
        validation_ok = case.get("expected_validation_status") is None or (
            result.validation is not None
            and result.validation.status == case["expected_validation_status"]
        )
        clarification_ok = case.get("expects_clarification") is None or (
            bool(result.task_plan and result.task_plan.clarification_question)
            == bool(case["expects_clarification"])
        )
        numeric_ok = True
        if case.get("expected_numeric") and result.intent is not None:
            expected = case["expected_numeric"]
            records = FinancialQueryTool().run(result.intent).data.get("records", [])
            matches = [
                row
                for row in records
                if row["report_year"] == expected["year"]
                and row["metric_code"] == expected["metric"]
                and (
                    expected.get("stock_code") is None
                    or row["stock_code"] == expected["stock_code"]
                )
            ]
            numeric_ok = (
                bool(matches)
                and abs(float(matches[0]["metric_value"]) - expected["value"])
                <= expected["tolerance"]
            )
        success = all(
            (
                status_ok,
                company_ok,
                metric_ok,
                tool_ok,
                citation_ok,
                chart_ok,
                numeric_ok,
                strategy_ok,
                validation_ok,
                clarification_ok,
            )
        )
        rows.append(
            {
                "id": case["id"],
                "category": case.get("category", "uncategorized"),
                "label_status": case.get("label_status", "unspecified"),
                "status": result.status,
                "status_ok": status_ok,
                "company_ok": company_ok,
                "metric_ok": metric_ok,
                "tool_selection_ok": tool_ok,
                "plan_strategy_ok": strategy_ok,
                "validation_status_ok": validation_ok,
                "clarification_ok": clarification_ok,
                "citation_ok": citation_ok,
                "chart_ok": chart_ok,
                "numeric_exact_match": numeric_ok,
                "task_success": success,
                "latency_ms": round(latency, 2),
                "actual_tools": actual_tools,
                "errors": result.errors,
            }
        )

    numeric_rows = [
        row
        for row in rows
        if next(case for case in cases if case["id"] == row["id"]).get("expected_numeric")
    ]
    category_rows: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        category_rows[row["category"]].append(row)
    latencies = [row["latency_ms"] for row in rows]
    summary = {
        "dataset": str(dataset_path),
        "cases": len(rows),
        "intent_accuracy": mean(1 if row["company_ok"] and row["metric_ok"] else 0 for row in rows),
        "tool_selection_accuracy": mean(1 if row["tool_selection_ok"] else 0 for row in rows),
        "citation_coverage": mean(1 if row["citation_ok"] else 0 for row in rows),
        "sql_numeric_exact_match": mean(
            1 if row["numeric_exact_match"] else 0 for row in numeric_rows
        )
        if numeric_rows
        else 1.0,
        "task_success_rate": mean(1 if row["task_success"] else 0 for row in rows),
        "latency_ms": {
            "average": round(mean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "p99": round(percentile(latencies, 0.99), 2),
            "max": round(max(latencies), 2),
        },
        "llm_mode": "real-provider" if use_llm else "deterministic-fallback",
        "category_summary": {
            category: {
                "cases": len(items),
                "task_success_rate": mean(1 if item["task_success"] else 0 for item in items),
                "average_latency_ms": round(mean(item["latency_ms"] for item in items), 2),
            }
            for category, items in sorted(category_rows.items())
        },
        "results": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evals/dataset_demo.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/report.json"))
    parser.add_argument(
        "--use-llm", action="store_true", help="使用真实 LLM；默认用确定性模式避免批量消耗"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.dataset, args.output, use_llm=args.use_llm), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
