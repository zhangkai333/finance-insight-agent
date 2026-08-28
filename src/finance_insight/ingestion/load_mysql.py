"""Load the MVP CSV into MySQL 8 when a MySQL service is available.

The script is intentionally separate from the SQLite loader because MySQL uses
DECIMAL/JSON types and different upsert placeholders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

from finance_insight.ingestion.load_sqlite import METRIC_METADATA, as_int, as_number


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV 没有数据: {csv_path}")
    return rows


def execute_schema(connection, schema_path: Path) -> None:
    schema = schema_path.read_text(encoding="utf-8")
    with connection.cursor() as cursor:
        for statement in schema.split(";" + "\n"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)


def load_rows(connection, rows: list[dict[str, str]], csv_path: Path) -> dict[str, int]:
    source_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    batch_id = f"mvp_csv_{source_sha256[:16]}"
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO ingestion_batches (batch_id, source_path, source_sha256, row_count, status)
               VALUES (%s, %s, %s, %s, 'loading')
               ON DUPLICATE KEY UPDATE source_path = VALUES(source_path),
                 source_sha256 = VALUES(source_sha256), row_count = VALUES(row_count),
                 status = 'loading', error_message = NULL""",
            (batch_id, str(csv_path.resolve()), source_sha256, len(rows)),
        )
        for source_row_number, row in enumerate(rows, start=2):
            cursor.execute(
                """INSERT INTO raw_financial_rows
                   (batch_id, source_row_number, stock_code, period_code, report_year, metric_code, raw_payload)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE stock_code = VALUES(stock_code),
                     period_code = VALUES(period_code), report_year = VALUES(report_year),
                     metric_code = VALUES(metric_code), raw_payload = VALUES(raw_payload)""",
                (batch_id, source_row_number, row["stock_code"], row["period_code"],
                 as_int(row["report_year"]), row["metric_code"],
                 json.dumps(row, ensure_ascii=False, sort_keys=True)),
            )
        for row in rows:
            cursor.execute(
                """INSERT INTO companies (stock_code, company_name)
                   VALUES (%s, %s)
                   ON DUPLICATE KEY UPDATE company_name = VALUES(company_name)""",
                (row["stock_code"], row["company_name"]),
            )
        cursor.execute("SELECT stock_code, company_id FROM companies")
        companies = dict(cursor.fetchall())
        for row in rows:
            cursor.execute(
                """INSERT INTO report_periods (period_code, report_year, report_quarter, period_label)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE period_label = VALUES(period_label)""",
                (row["period_code"], as_int(row["report_year"]), as_int(row["report_quarter"]),
                 f"{row['period_code']}{row['report_year']}"),
            )
        cursor.execute("SELECT period_code, report_year, report_quarter, report_period_id FROM report_periods")
        periods = {(code, year, quarter): period_id for code, year, quarter, period_id in cursor.fetchall()}
        for code, meta in METRIC_METADATA.items():
            cursor.execute(
                """INSERT INTO metric_definitions
                   (metric_code, metric_name, category, default_unit, value_type, formula)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE metric_name = VALUES(metric_name), category = VALUES(category),
                     default_unit = VALUES(default_unit), value_type = VALUES(value_type), formula = VALUES(formula)""",
                (code, meta["name"], meta["category"], meta["unit"], meta["value_type"], meta["formula"] or None),
            )
        cursor.execute("SELECT metric_code, metric_id FROM metric_definitions")
        metrics = dict(cursor.fetchall())
        for row in rows:
            code = row["metric_code"]
            period_key = (row["period_code"], as_int(row["report_year"]), as_int(row["report_quarter"]))
            cursor.execute(
                """INSERT INTO financial_facts
                   (company_id, report_period_id, metric_id, metric_value, normalized_unit,
                    raw_value, raw_unit, accounting_scope, value_type, source_file,
                    source_page, extraction_method, quality_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE metric_value = VALUES(metric_value),
                     normalized_unit = VALUES(normalized_unit), raw_value = VALUES(raw_value),
                     raw_unit = VALUES(raw_unit), accounting_scope = VALUES(accounting_scope),
                     value_type = VALUES(value_type), source_file = VALUES(source_file),
                     source_page = VALUES(source_page), extraction_method = VALUES(extraction_method),
                     quality_status = VALUES(quality_status)""",
                (companies[row["stock_code"]], periods[period_key], metrics[code],
                 as_number(row["normalized_value"]), row["normalized_unit"],
                 as_number(row["raw_value"]), row["raw_unit"], "consolidated",
                 METRIC_METADATA[code]["value_type"], row["source_file"],
                 as_int(row["source_page"]), row["extraction_method"], row["quality_status"]),
            )
        cursor.execute("UPDATE ingestion_batches SET status = 'loaded' WHERE batch_id = %s", (batch_id,))
    return {"batch_id": batch_id, "csv_rows": len(rows), "facts": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path("db/schema.mysql.sql"))
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "finance_insight"))
    args = parser.parse_args()
    try:
        import pymysql
    except ImportError as exc:
        raise SystemExit("未安装 pymysql；MySQL 服务可用后执行: pip install pymysql") from exc
    connection = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        database=args.database, charset="utf8mb4", autocommit=False,
    )
    try:
        execute_schema(connection, args.schema)
        summary = load_rows(connection, read_rows(args.csv), args.csv)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()


