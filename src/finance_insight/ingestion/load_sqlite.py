"""Load the Phase 1 MVP financial facts into a local SQLite database."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

METRIC_METADATA: dict[str, dict[str, str]] = {
    "revenue": {"name": "营业收入", "category": "规模", "unit": "万元", "value_type": "reported", "formula": ""},
    "net_profit_attributable": {"name": "归属于上市公司股东的净利润", "category": "盈利", "unit": "万元", "value_type": "reported", "formula": ""},
    "net_profit_excl_non_recurring": {"name": "归属于上市公司股东的扣除非经常性损益的净利润", "category": "盈利", "unit": "万元", "value_type": "reported", "formula": ""},
    "operating_cash_flow": {"name": "经营活动产生的现金流量净额", "category": "现金流", "unit": "万元", "value_type": "reported", "formula": ""},
    "eps": {"name": "基本每股收益", "category": "每股指标", "unit": "元/股", "value_type": "reported", "formula": ""},
    "roe": {"name": "加权平均净资产收益率", "category": "盈利能力", "unit": "%", "value_type": "reported", "formula": ""},
    "total_assets": {"name": "总资产", "category": "规模", "unit": "万元", "value_type": "reported", "formula": ""},
    "net_assets": {"name": "归属于上市公司股东的净资产", "category": "规模", "unit": "万元", "value_type": "reported", "formula": ""},
    "net_margin": {"name": "净利率（计算）", "category": "盈利能力", "unit": "%", "value_type": "derived", "formula": "net_profit_attributable / revenue * 100"},
    "operating_cash_margin": {"name": "经营现金流/营业收入（计算）", "category": "现金流", "unit": "%", "value_type": "derived", "formula": "operating_cash_flow / revenue * 100"},
}


def as_int(value: str) -> int:
    return int(float(value))


def as_number(value: str) -> float:
    return float(value)


def create_database(connection: sqlite3.Connection, schema_path: Path) -> None:
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    connection.execute("PRAGMA foreign_keys = ON")


def load_csv(connection: sqlite3.Connection, csv_path: Path) -> dict[str, int]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV 没有数据: {csv_path}")

    source_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    batch_id = f"mvp_csv_{source_sha256[:16]}"
    connection.execute(
        """INSERT INTO ingestion_batches (batch_id, source_path, source_sha256, row_count, status)
           VALUES (?, ?, ?, ?, 'loading')
           ON CONFLICT(batch_id) DO UPDATE SET
             source_path = excluded.source_path,
             source_sha256 = excluded.source_sha256,
             row_count = excluded.row_count,
             status = 'loading',
             error_message = NULL""",
        (batch_id, str(csv_path.resolve()), source_sha256, len(rows)),
    )
    for source_row_number, row in enumerate(rows, start=2):
        connection.execute(
            """INSERT INTO raw_financial_rows
               (batch_id, source_row_number, stock_code, period_code, report_year, metric_code, raw_payload)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(batch_id, source_row_number) DO UPDATE SET
                 stock_code = excluded.stock_code,
                 period_code = excluded.period_code,
                 report_year = excluded.report_year,
                 metric_code = excluded.metric_code,
                 raw_payload = excluded.raw_payload""",
            (
                batch_id,
                source_row_number,
                row["stock_code"],
                row["period_code"],
                as_int(row["report_year"]),
                row["metric_code"],
                json.dumps(row, ensure_ascii=False, sort_keys=True),
            ),
        )

    companies: dict[str, int] = {}
    for row in rows:
        connection.execute(
            """INSERT INTO companies (stock_code, company_name)
               VALUES (?, ?)
               ON CONFLICT(stock_code) DO UPDATE SET company_name = excluded.company_name""",
            (row["stock_code"], row["company_name"]),
        )
    for stock_code, company_name in connection.execute(
        "SELECT stock_code, company_name FROM companies ORDER BY stock_code"
    ):
        companies[stock_code] = connection.execute(
            "SELECT company_id FROM companies WHERE stock_code = ?", (stock_code,)
        ).fetchone()[0]

    periods: dict[tuple[str, int, int], int] = {}
    for row in rows:
        period_key = (row["period_code"], as_int(row["report_year"]), as_int(row["report_quarter"]))
        connection.execute(
            """INSERT INTO report_periods
               (period_code, report_year, report_quarter, period_label)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(period_code, report_year, report_quarter) DO UPDATE SET period_label = excluded.period_label""",
            (*period_key, f"{period_key[0]}{period_key[1]}"),
        )
    for period_code, report_year, report_quarter in connection.execute(
        "SELECT period_code, report_year, report_quarter FROM report_periods"
    ):
        periods[(period_code, report_year, report_quarter)] = connection.execute(
            """SELECT report_period_id FROM report_periods
               WHERE period_code = ? AND report_year = ? AND report_quarter = ?""",
            (period_code, report_year, report_quarter),
        ).fetchone()[0]

    for metric_code, meta in METRIC_METADATA.items():
        connection.execute(
            """INSERT INTO metric_definitions
               (metric_code, metric_name, category, default_unit, value_type, formula)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(metric_code) DO UPDATE SET
                 metric_name = excluded.metric_name,
                 category = excluded.category,
                 default_unit = excluded.default_unit,
                 value_type = excluded.value_type,
                 formula = excluded.formula""",
            (metric_code, meta["name"], meta["category"], meta["unit"], meta["value_type"], meta["formula"] or None),
        )
    metric_ids = {
        metric_code: metric_id
        for metric_code, metric_id in connection.execute(
            "SELECT metric_code, metric_id FROM metric_definitions"
        )
    }

    fact_sql = """INSERT INTO financial_facts (
        company_id, report_period_id, metric_id, metric_value, normalized_unit,
        raw_value, raw_unit, accounting_scope, value_type, source_file,
        source_page, extraction_method, quality_status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(company_id, report_period_id, metric_id) DO UPDATE SET
        metric_value = excluded.metric_value,
        normalized_unit = excluded.normalized_unit,
        raw_value = excluded.raw_value,
        raw_unit = excluded.raw_unit,
        accounting_scope = excluded.accounting_scope,
        value_type = excluded.value_type,
        source_file = excluded.source_file,
        source_page = excluded.source_page,
        extraction_method = excluded.extraction_method,
        quality_status = excluded.quality_status"""
    for row in rows:
        period_key = (row["period_code"], as_int(row["report_year"]), as_int(row["report_quarter"]))
        metric_code = row["metric_code"]
        if metric_code not in metric_ids:
            raise ValueError(f"未定义指标: {metric_code}")
        connection.execute(
            fact_sql,
            (
                companies[row["stock_code"]],
                periods[period_key],
                metric_ids[metric_code],
                as_number(row["normalized_value"]),
                row["normalized_unit"],
                as_number(row["raw_value"]),
                row["raw_unit"],
                "consolidated",
                METRIC_METADATA[metric_code]["value_type"],
                row["source_file"],
                as_int(row["source_page"]),
                row["extraction_method"],
                row["quality_status"],
            ),
        )

    connection.execute(
        "UPDATE ingestion_batches SET status = 'loaded', error_message = NULL WHERE batch_id = ?",
        (batch_id,),
    )
    return {
        "batch_id": batch_id,
        "csv_rows": len(rows),
        "companies": connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
        "periods": connection.execute("SELECT COUNT(*) FROM report_periods").fetchone()[0],
        "metrics": connection.execute("SELECT COUNT(*) FROM metric_definitions").fetchone()[0],
        "raw_rows": connection.execute("SELECT COUNT(*) FROM raw_financial_rows").fetchone()[0],
        "facts": connection.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path("db/schema.sql"))
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(args.db)
    try:
        with connection:
            create_database(connection, args.schema)
            summary = load_csv(connection, args.csv)
    finally:
        connection.close()
    print(summary)


if __name__ == "__main__":
    main()
