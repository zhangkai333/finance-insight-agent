"""Synchronize the portable SQLite finance demo into the MySQL runtime schema."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


def read_snapshot(sqlite_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 数据库不存在: {sqlite_path}")
    with sqlite3.connect(sqlite_path) as connection:
        connection.row_factory = sqlite3.Row
        return {
            "companies": [
                dict(row)
                for row in connection.execute(
                    "SELECT stock_code,company_name,exchange,industry,is_target FROM companies"
                )
            ],
            "periods": [
                dict(row)
                for row in connection.execute(
                    "SELECT period_code,report_year,report_quarter,period_label,period_start,period_end FROM report_periods"
                )
            ],
            "metrics": [
                dict(row)
                for row in connection.execute(
                    "SELECT metric_code,metric_name,category,default_unit,value_type,formula,description FROM metric_definitions"
                )
            ],
            "facts": [
                dict(row)
                for row in connection.execute(
                    """SELECT c.stock_code,rp.period_code,rp.report_year,rp.report_quarter,
                          md.metric_code,ff.metric_value,ff.normalized_unit,ff.raw_value,
                          ff.raw_unit,ff.accounting_scope,ff.value_type,ff.source_file,
                          ff.source_page,ff.extraction_method,ff.quality_status
                   FROM financial_facts ff
                   JOIN companies c ON c.company_id=ff.company_id
                   JOIN report_periods rp ON rp.report_period_id=ff.report_period_id
                   JOIN metric_definitions md ON md.metric_id=ff.metric_id"""
                )
            ],
        }


def connect_with_retry(*, attempts: int = 30, delay: float = 2.0):
    import pymysql

    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return pymysql.connect(
                host=os.getenv("MYSQL_HOST", "mysql"),
                port=int(os.getenv("MYSQL_PORT", "3306")),
                user=os.getenv("MYSQL_USER", "finance"),
                password=os.getenv("MYSQL_PASSWORD", "change-me"),
                database=os.getenv("MYSQL_DATABASE", "finance_insight"),
                charset="utf8mb4",
                autocommit=False,
            )
        except Exception as exc:
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"无法连接 MySQL: {last_error}")


def sync(connection, snapshot: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    with connection.cursor() as cursor:
        for row in snapshot["companies"]:
            cursor.execute(
                """INSERT INTO companies (stock_code,company_name,exchange,industry,is_target)
                   VALUES (%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE company_name=VALUES(company_name),exchange=VALUES(exchange),
                     industry=VALUES(industry),is_target=VALUES(is_target)""",
                (
                    row["stock_code"],
                    row["company_name"],
                    row["exchange"],
                    row["industry"],
                    row["is_target"],
                ),
            )
        for row in snapshot["periods"]:
            cursor.execute(
                """INSERT INTO report_periods
                   (period_code,report_year,report_quarter,period_label,period_start,period_end)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE period_label=VALUES(period_label),period_start=VALUES(period_start),
                     period_end=VALUES(period_end)""",
                (
                    row["period_code"],
                    row["report_year"],
                    row["report_quarter"],
                    row["period_label"],
                    row["period_start"],
                    row["period_end"],
                ),
            )
        for row in snapshot["metrics"]:
            cursor.execute(
                """INSERT INTO metric_definitions
                   (metric_code,metric_name,category,default_unit,value_type,formula,description)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE metric_name=VALUES(metric_name),category=VALUES(category),
                     default_unit=VALUES(default_unit),value_type=VALUES(value_type),formula=VALUES(formula),
                     description=VALUES(description)""",
                (
                    row["metric_code"],
                    row["metric_name"],
                    row["category"],
                    row["default_unit"],
                    row["value_type"],
                    row["formula"],
                    row["description"],
                ),
            )
        cursor.execute("SELECT stock_code,company_id FROM companies")
        companies = dict(cursor.fetchall())
        cursor.execute(
            "SELECT period_code,report_year,report_quarter,report_period_id FROM report_periods"
        )
        periods = {
            (code, year, quarter): period_id for code, year, quarter, period_id in cursor.fetchall()
        }
        cursor.execute("SELECT metric_code,metric_id FROM metric_definitions")
        metrics = dict(cursor.fetchall())
        for row in snapshot["facts"]:
            cursor.execute(
                """INSERT INTO financial_facts
                   (company_id,report_period_id,metric_id,metric_value,normalized_unit,raw_value,
                    raw_unit,accounting_scope,value_type,source_file,source_page,extraction_method,quality_status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE metric_value=VALUES(metric_value),normalized_unit=VALUES(normalized_unit),
                     raw_value=VALUES(raw_value),raw_unit=VALUES(raw_unit),accounting_scope=VALUES(accounting_scope),
                     value_type=VALUES(value_type),source_file=VALUES(source_file),source_page=VALUES(source_page),
                     extraction_method=VALUES(extraction_method),quality_status=VALUES(quality_status)""",
                (
                    companies[row["stock_code"]],
                    periods[(row["period_code"], row["report_year"], row["report_quarter"])],
                    metrics[row["metric_code"]],
                    row["metric_value"],
                    row["normalized_unit"],
                    row["raw_value"],
                    row["raw_unit"],
                    row["accounting_scope"],
                    row["value_type"],
                    row["source_file"],
                    row["source_page"],
                    row["extraction_method"],
                    row["quality_status"],
                ),
            )
    return {key: len(value) for key, value in snapshot.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path(os.getenv("FINANCE_DB", "/app/data/finance_insight.sqlite3")),
    )
    args = parser.parse_args()
    snapshot = read_snapshot(args.sqlite)
    connection = connect_with_retry()
    try:
        summary = sync(connection, snapshot)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(json.dumps({"status": "synced", **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
