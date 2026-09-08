"""Run a bounded SQLite/MySQL backend contract and failure-fallback check."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from finance_insight.config import Settings
from finance_insight.intent_parser import parse_intent
from finance_insight.tools import FinancialQueryTool


def signature(result: Any) -> list[tuple[Any, ...]]:
    return [
        (row.get("stock_code"), row.get("report_year"), row.get("metric_code"), float(row["metric_value"]))
        for row in result.data.get("records", [])
    ]


def result_metadata(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "requested_backend": result.data.get("requested_backend"),
        "effective_backend": result.data.get("backend"),
        "records": len(signature(result)),
        "fallback_used": result.fallback_used,
        "fallback_reason": result.data.get("fallback_reason"),
        "connection_pool": result.data.get("connection_pool"),
    }


def run(sqlite_path: Path, output: Path, mysql_host: str, mysql_port: int) -> dict[str, Any]:
    intent = parse_intent("查询凯莱英2022到2024年营业收入趋势", Settings(finance_db=sqlite_path))
    sqlite_result = FinancialQueryTool(Settings(finance_db=sqlite_path, finance_backend="sqlite")).run(intent)
    fallback_config = Settings(
        finance_db=sqlite_path,
        finance_backend="mysql",
        mysql_host=mysql_host,
        mysql_port=mysql_port,
        mysql_connect_timeout_seconds=1,
        mysql_fallback_to_sqlite=True,
    )
    fallback_result = FinancialQueryTool(fallback_config).run(intent)
    mysql_config = Settings(
        finance_db=sqlite_path,
        finance_backend="mysql",
        mysql_host=mysql_host,
        mysql_port=mysql_port,
        mysql_connect_timeout_seconds=1,
        mysql_pool_acquire_timeout_seconds=1,
        mysql_fallback_to_sqlite=False,
    )
    mysql_result = FinancialQueryTool(mysql_config).run(intent)
    mysql_reachable = mysql_result.status == "success" and mysql_result.data.get("backend") == "mysql"
    real_mysql: dict[str, Any] = {
        "status": "PASS" if mysql_reachable else "NOT_RUN",
        "result": result_metadata(mysql_result),
    }
    if mysql_reachable:
        real_mysql["same_result_signature"] = signature(sqlite_result) == signature(mysql_result)
        if not real_mysql["same_result_signature"]:
            real_mysql["status"] = "FAIL"
    else:
        real_mysql["reason"] = "MySQL service is unreachable or returned a query error"

    fallback_passed = (
        sqlite_result.status == "success"
        and fallback_result.fallback_used
        and fallback_result.data.get("backend") == "sqlite"
        and bool(fallback_result.data.get("fallback_reason"))
        and signature(sqlite_result) == signature(fallback_result)
    )
    payload: dict[str, Any] = {
        "status": "PASS" if fallback_passed and real_mysql["status"] != "FAIL" else "FAIL",
        "scope": "same question and signature; injected outage always runs, live MySQL runs only when reachable",
        "sqlite": result_metadata(sqlite_result),
        "injected_mysql_outage": {
            "status": "PASS" if fallback_passed else "FAIL",
            "result": result_metadata(fallback_result),
            "same_result_signature": signature(sqlite_result) == signature(fallback_result),
        },
        "real_mysql": real_mysql,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, default=Path("data/finance_insight.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/mvp_dataset/backend_validation.json"))
    parser.add_argument("--mysql-host", default="127.0.0.1")
    parser.add_argument("--mysql-port", type=int, default=1)
    args = parser.parse_args()
    result = run(args.sqlite, args.output, args.mysql_host, args.mysql_port)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
