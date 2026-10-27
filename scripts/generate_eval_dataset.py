from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / ".demo-data" / "finance_insight.sqlite3"
DEFAULT_OUTPUT = ROOT / ".demo-data" / "evaluation" / "dataset_extended_draft.json"

COMPANIES = [
    ("002821", "凯莱英"),
    ("300244", "迪安诊断"),
    ("300347", "泰格医药"),
    ("301033", "迈普医学"),
    ("301080", "百普赛斯"),
    ("301096", "百诚医药"),
    ("603127", "昭衍新药"),
    ("603259", "药明康德"),
    ("688222", "成都先导"),
    ("688276", "百克生物"),
]

METRICS = [
    ("revenue", "营业收入"),
    ("net_profit_attributable", "归母净利润"),
    ("net_profit_excl_non_recurring", "扣非净利润"),
    ("operating_cash_flow", "经营活动现金流"),
    ("eps", "每股收益"),
    ("roe", "ROE"),
    ("total_assets", "总资产"),
    ("net_assets", "归属于上市公司股东的净资产"),
    ("net_margin", "销售净利率"),
    ("operating_cash_margin", "经营现金流率"),
]


def numeric_expectation(
    connection: sqlite3.Connection, stock_code: str, year: int, metric: str
) -> dict:
    row = connection.execute(
        """SELECT ff.metric_value
           FROM financial_facts ff
           JOIN companies c ON c.company_id = ff.company_id
           JOIN report_periods rp ON rp.report_period_id = ff.report_period_id
           JOIN metric_definitions md ON md.metric_id = ff.metric_id
           WHERE c.stock_code = ? AND rp.report_year = ? AND rp.period_code = 'FY'
             AND md.metric_code = ?""",
        (stock_code, year, metric),
    ).fetchone()
    if row is None:
        raise ValueError(f"缺少标注事实: {stock_code}/{year}/{metric}")
    return {
        "stock_code": stock_code,
        "year": year,
        "metric": metric,
        "value": float(row[0]),
        "tolerance": 1e-6,
    }


def base_case(
    case_id: str,
    category: str,
    question: str,
    tools: list[str],
    company: str | None,
    metrics: list[str],
) -> dict:
    return {
        "id": case_id,
        "category": category,
        "label_status": "auto_draft_requires_human_review",
        "question": question,
        "expected_tools": tools,
        "expected_company": company,
        "expected_metrics": metrics,
        "min_citations": 0,
        "min_charts": 0,
    }


def generate(db_path: Path) -> list[dict]:
    connection = sqlite3.connect(db_path)
    cases: list[dict] = []
    try:
        # 20 个单点精确问数：覆盖所有公司、全部指标和三个年度。
        for index, (stock_code, company) in enumerate(COMPANIES):
            for offset in range(2):
                metric_code, metric_name = METRICS[(index * 2 + offset) % len(METRICS)]
                year = 2022 + ((index + offset) % 3)
                case = base_case(
                    f"point_{index * 2 + offset + 1:02d}",
                    "point_query",
                    f"查询{company}{year}年{metric_name}",
                    ["financial_query"],
                    stock_code,
                    [metric_code],
                )
                case["expected_numeric"] = numeric_expectation(
                    connection, stock_code, year, metric_code
                )
                cases.append(case)

        # 10 个跨年度趋势问题。
        for index, (stock_code, company) in enumerate(COMPANIES):
            metric_code, metric_name = METRICS[index]
            cases.append(
                base_case(
                    f"trend_{index + 1:02d}",
                    "trend_analysis",
                    f"分析{company}2022—2024年{metric_name}趋势",
                    ["financial_query", "financial_analysis"],
                    stock_code,
                    [metric_code],
                )
            )

        # 10 个全公司排名问题。
        for index, (metric_code, metric_name) in enumerate(METRICS):
            cases.append(
                base_case(
                    f"ranking_{index + 1:02d}",
                    "ranking",
                    f"查询2024年十家公司{metric_name}排名",
                    ["financial_query"],
                    None,
                    [metric_code],
                )
            )

        # 10 个需要年报依据的异常解释问题。
        for index, (stock_code, company) in enumerate(COMPANIES):
            case = base_case(
                f"rag_{index + 1:02d}",
                "rag_explanation",
                f"分析{company}2022—2024年营业收入异常变化，并结合年报解释原因和依据",
                ["financial_query", "financial_analysis", "annual_report_search"],
                stock_code,
                ["revenue"],
            )
            case["min_citations"] = 1
            cases.append(case)

        # 10 个趋势图问题。
        for index, (stock_code, company) in enumerate(COMPANIES):
            metric_code, metric_name = METRICS[(index + 5) % len(METRICS)]
            case = base_case(
                f"chart_{index + 1:02d}",
                "chart",
                f"绘制{company}2022—2024年{metric_name}趋势图",
                ["financial_query", "financial_analysis", "chart_generation"],
                stock_code,
                [metric_code],
            )
            case["min_charts"] = 1
            cases.append(case)
    finally:
        connection.close()

    if len(cases) != 60 or len({case["id"] for case in cases}) != 60:
        raise AssertionError("扩展评测集必须包含 60 条唯一问题")
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 60 条可复现的评测问题初稿")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    cases = generate(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cases": len(cases),
                "label_status": "auto_draft_requires_human_review",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
