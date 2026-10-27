"""Run the first three acceptance queries against the Phase 2 SQLite database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    try:
        revenue_sql = """SELECT stock_code, company_name, report_year, revenue, net_margin
            FROM v_annual_financial_summary WHERE stock_code = '002821' ORDER BY report_year"""
        roe_sql = """SELECT stock_code, company_name, report_year, roe
            FROM v_annual_financial_summary WHERE stock_code = '002821' ORDER BY report_year"""
        ranking_sql = """SELECT stock_code, company_name, report_year, revenue
            FROM v_annual_financial_summary WHERE report_year = 2024 ORDER BY revenue DESC"""
        result = {
            "revenue_trend_kailaiying": [dict(row) for row in con.execute(revenue_sql).fetchall()],
            "roe_trend_kailaiying": [dict(row) for row in con.execute(roe_sql).fetchall()],
            "revenue_ranking_2024": [dict(row) for row in con.execute(ranking_sql).fetchall()],
        }
        counts = {
            "companies": con.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "periods": con.execute("SELECT COUNT(*) FROM report_periods").fetchone()[0],
            "metrics": con.execute("SELECT COUNT(*) FROM metric_definitions").fetchone()[0],
            "facts": con.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0],
            "ingestion_batches": con.execute("SELECT COUNT(*) FROM ingestion_batches").fetchone()[
                0
            ],
            "raw_rows": con.execute("SELECT COUNT(*) FROM raw_financial_rows").fetchone()[0],
            "quality_issues": con.execute("SELECT COUNT(*) FROM data_quality_issues").fetchone()[0],
            "annual_summary_rows": con.execute(
                "SELECT COUNT(*) FROM v_annual_financial_summary"
            ).fetchone()[0],
        }
    finally:
        con.close()
    if len(result["revenue_trend_kailaiying"]) != 3:
        raise SystemExit("凯莱英收入趋势应有 3 行")
    if len(result["roe_trend_kailaiying"]) != 3:
        raise SystemExit("凯莱英 ROE 趋势应有 3 行")
    if len(result["revenue_ranking_2024"]) != 10:
        raise SystemExit("2024 年公司收入排名应有 10 行")
    expected = {
        "companies": 10,
        "periods": 3,
        "metrics": 10,
        "facts": 300,
        "ingestion_batches": 1,
        "raw_rows": 300,
        "quality_issues": 0,
        "annual_summary_rows": 30,
    }
    if counts != expected:
        raise SystemExit(f"数据库计数不符合预期: {counts}")
    payload = {"counts": counts, "queries": result, "status": "PASS"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
