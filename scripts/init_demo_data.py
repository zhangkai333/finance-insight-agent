"""Create a fully synthetic demo dataset for FinanceInsight Agent.

The generated values and narrative text are fictional and are intended only for
software demonstrations. Existing databases are never replaced unless --force is
provided explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from finance_insight.ingestion.build_vector_index import build as build_vector_index
from finance_insight.ingestion.load_sqlite import METRIC_METADATA

COMPANIES: tuple[tuple[str, str, str], ...] = (
    ("002821", "凯莱英", "医药研发服务"),
    ("301080", "百普赛斯", "生物试剂"),
    ("301033", "迈普医学", "医疗器械"),
    ("301096", "百诚医药", "医药研发服务"),
    ("300347", "泰格医药", "临床研究服务"),
    ("300244", "迪安诊断", "医学诊断服务"),
    ("603127", "昭衍新药", "药物安全评价"),
    ("603259", "药明康德", "医药研发服务"),
    ("688222", "成都先导", "药物发现服务"),
    ("688276", "百克生物", "生物制品"),
)
YEARS = (2022, 2023, 2024)
GENERATOR_VERSION = "synthetic-demo-v1"
QUALITY_STATUS = "synthetic_demo_only"


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _financial_values(company_index: int, year: int) -> dict[str, float]:
    """Return deterministic fictional metrics; no value is sourced from a filing."""
    year_index = year - YEARS[0]
    base_revenue = 72_000 + company_index * 18_500
    normal_factors = (1.0, 1.11 + (company_index % 3) * 0.015, 1.24 + (company_index % 4) * 0.02)
    # The first company intentionally has a visible dip so anomaly/chart demos are meaningful.
    factors = (1.0, 0.74, 0.93) if company_index == 0 else normal_factors
    revenue = base_revenue * factors[year_index]

    margin = 13.5 + company_index * 0.42 + (-1.8 if year == 2023 and company_index % 3 == 0 else year_index * 0.35)
    cash_margin = 15.2 + company_index * 0.31 + (-2.4 if year == 2023 and company_index % 4 == 0 else year_index * 0.45)
    net_profit = revenue * margin / 100
    cash_flow = revenue * cash_margin / 100
    total_assets = revenue * (2.05 + company_index * 0.025)
    net_assets = total_assets * (0.43 + (company_index % 3) * 0.018)
    roe = 11.5 + company_index * 0.55 + year_index * 0.8
    if company_index == 0:
        roe = (16.2, 8.7, 12.4)[year_index]

    return {
        "revenue": _round(revenue),
        "net_profit_attributable": _round(net_profit),
        "net_profit_excl_non_recurring": _round(net_profit * (0.88 + (company_index % 2) * 0.025)),
        "operating_cash_flow": _round(cash_flow),
        "eps": _round((0.58 + company_index * 0.09) * factors[year_index], 4),
        "roe": _round(roe, 4),
        "total_assets": _round(total_assets),
        "net_assets": _round(net_assets),
        "net_margin": _round(net_profit / revenue * 100, 4),
        "operating_cash_margin": _round(cash_flow / revenue * 100, 4),
    }


def _create_finance_database(db_path: Path, schema_path: Path) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    try:
        con.executescript(schema_path.read_text(encoding="utf-8"))
        con.execute("PRAGMA foreign_keys = ON")
        batch_id = "synthetic_demo_v1"
        payload_marker = json.dumps(
            {"generator": GENERATOR_VERSION, "notice": "fictional demo data; not actual company results"},
            ensure_ascii=False,
            sort_keys=True,
        )
        source_sha256 = hashlib.sha256(payload_marker.encode("utf-8")).hexdigest()
        con.execute(
            """INSERT INTO ingestion_batches
               (batch_id, source_path, source_sha256, row_count, status)
               VALUES (?, ?, ?, 300, 'loaded')""",
            (batch_id, "synthetic://finance-insight/demo-v1", source_sha256),
        )

        metric_ids: dict[str, int] = {}
        for metric_code, metadata in METRIC_METADATA.items():
            cursor = con.execute(
                """INSERT INTO metric_definitions
                   (metric_code, metric_name, category, default_unit, value_type, formula, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    metric_code,
                    metadata["name"],
                    metadata["category"],
                    metadata["unit"],
                    metadata["value_type"],
                    metadata["formula"] or None,
                    "完全合成的开源演示指标，不代表任何上市公司的真实数据。",
                ),
            )
            metric_ids[metric_code] = int(cursor.lastrowid)

        period_ids: dict[int, int] = {}
        for year in YEARS:
            cursor = con.execute(
                """INSERT INTO report_periods
                   (period_code, report_year, report_quarter, period_label, period_start, period_end)
                   VALUES ('FY', ?, 4, ?, ?, ?)""",
                (year, f"FY {year}（合成演示）", f"{year}-01-01", f"{year}-12-31"),
            )
            period_ids[year] = int(cursor.lastrowid)

        source_row = 1
        for company_index, (stock_code, company_name, industry) in enumerate(COMPANIES):
            cursor = con.execute(
                """INSERT INTO companies (stock_code, company_name, exchange, industry)
                   VALUES (?, ?, ?, ?)""",
                (stock_code, company_name, "SYNTHETIC_DEMO", industry),
            )
            company_id = int(cursor.lastrowid)
            for year in YEARS:
                values = _financial_values(company_index, year)
                for metric_code, metric_value in values.items():
                    metadata = METRIC_METADATA[metric_code]
                    raw_payload = {
                        "stock_code": stock_code,
                        "company_name": company_name,
                        "year": year,
                        "metric_code": metric_code,
                        "value": metric_value,
                        "unit": metadata["unit"],
                        "synthetic": True,
                    }
                    con.execute(
                        """INSERT INTO raw_financial_rows
                           (batch_id, source_row_number, stock_code, period_code, report_year, metric_code, raw_payload)
                           VALUES (?, ?, ?, 'FY', ?, ?, ?)""",
                        (
                            batch_id,
                            source_row,
                            stock_code,
                            year,
                            metric_code,
                            json.dumps(raw_payload, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                    con.execute(
                        """INSERT INTO financial_facts
                           (company_id, report_period_id, metric_id, metric_value, normalized_unit,
                            raw_value, raw_unit, accounting_scope, value_type, source_file,
                            source_page, extraction_method, quality_status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'synthetic_demo', ?, ?, 1, ?, ?)""",
                        (
                            company_id,
                            period_ids[year],
                            metric_ids[metric_code],
                            metric_value,
                            metadata["unit"],
                            metric_value,
                            metadata["unit"],
                            metadata["value_type"],
                            "synthetic_demo_data",
                            GENERATOR_VERSION,
                            QUALITY_STATUS,
                        ),
                    )
                    source_row += 1
        con.commit()
        quick_check = con.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "path": str(db_path),
            "companies": con.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "periods": con.execute("SELECT COUNT(*) FROM report_periods").fetchone()[0],
            "metrics": con.execute("SELECT COUNT(*) FROM metric_definitions").fetchone()[0],
            "facts": con.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0],
            "quality_status": QUALITY_STATUS,
            "quick_check": quick_check,
        }
    finally:
        con.close()


def _synthetic_report_chunks(company_index: int, company_name: str) -> tuple[str, str]:
    themes = (
        "演示订单节奏调整与虚构产能爬坡",
        "合成产品组合升级与演示客户拓展",
        "虚构研发平台迭代与模拟交付效率改善",
    )
    theme = themes[company_index % len(themes)]
    operating = (
        f"【合成演示材料，不是真实年报】{company_name} 2024 年演示经营情况："
        f"本数据集设定公司围绕{theme}推进经营。演示收入、利润和现金流均由固定公式生成，"
        "仅用于验证 Agent 的数据库查询、趋势计算、检索引用和答案生成能力，不得用于投资判断。"
    )
    reason = (
        f"【合成演示材料，不是真实年报】{company_name} 指标变化的主要原因："
        "模型场景假定年度订单确认节奏、虚构产品结构、模拟产能利用率和演示研发投入发生变化。"
        "这些说明为原创测试文本，与该公司真实经营事实、公告或财务表现无关。"
    )
    return operating, reason


def _create_rag_database(db_path: Path, schema_path: Path, dimension: int) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    try:
        con.executescript(schema_path.read_text(encoding="utf-8"))
        con.execute("PRAGMA foreign_keys = ON")
        for company_index, (stock_code, company_name, _industry) in enumerate(COMPANIES):
            source_file = f"synthetic_demo_report_{stock_code}.txt"
            cursor = con.execute(
                """INSERT INTO documents
                   (stock_code, company_name, document_type, report_year, title,
                    source_file, source_path, page_count, parser)
                   VALUES (?, ?, 'synthetic_demo_report', 2024, ?, ?, ?, 2, ?)""",
                (
                    stock_code,
                    company_name,
                    f"{company_name} 2024 合成经营说明（非真实年报）",
                    source_file,
                    f"synthetic://finance-insight/{source_file}",
                    "synthetic_demo_generator",
                ),
            )
            document_id = int(cursor.lastrowid)
            for chunk_index, content in enumerate(_synthetic_report_chunks(company_index, company_name)):
                chunk_cursor = con.execute(
                    """INSERT INTO document_chunks
                       (document_id, page_number, chunk_index, content, char_count, section_hint)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        document_id,
                        chunk_index + 1,
                        chunk_index,
                        content,
                        len(content),
                        "演示经营情况" if chunk_index == 0 else "演示变化原因",
                    ),
                )
                chunk_id = int(chunk_cursor.lastrowid)
                con.execute(
                    """INSERT INTO document_chunks_fts
                       (chunk_id, document_id, content, page_number) VALUES (?, ?, ?, ?)""",
                    (chunk_id, document_id, content, chunk_index + 1),
                )
        con.commit()
    finally:
        con.close()

    vector_summary = build_vector_index(db_path, dimension=dimension)
    con = sqlite3.connect(db_path)
    try:
        quick_check = con.execute("PRAGMA quick_check").fetchone()[0]
        return {
            "path": str(db_path),
            "documents": con.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "chunks": con.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0],
            "vectors": vector_summary["vectors"],
            "dimension": vector_summary["dimension"],
            "quick_check": quick_check,
        }
    finally:
        con.close()


def initialize_demo_data(
    data_dir: Path,
    *,
    finance_schema: Path = PROJECT_ROOT / "db" / "schema.sql",
    rag_schema: Path = PROJECT_ROOT / "db" / "rag_schema.sql",
    force: bool = False,
    dimension: int = 256,
) -> dict[str, Any]:
    data_dir = data_dir.resolve()
    finance_db = data_dir / "finance_insight.sqlite3"
    rag_db = data_dir / "rag.sqlite3"
    existing = [path for path in (finance_db, rag_db) if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"拒绝覆盖已有数据库: {names}。若确认要替换为合成 Demo，请显式添加 --force。"
        )
    if not finance_schema.is_file() or not rag_schema.is_file():
        raise FileNotFoundError("找不到 db/schema.sql 或 db/rag_schema.sql，请从项目根目录运行。")

    data_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    temp_finance = data_dir / f".finance_insight.{token}.tmp.sqlite3"
    temp_rag = data_dir / f".rag.{token}.tmp.sqlite3"
    try:
        finance_summary = _create_finance_database(temp_finance, finance_schema)
        rag_summary = _create_rag_database(temp_rag, rag_schema, dimension)
        os.replace(temp_finance, finance_db)
        os.replace(temp_rag, rag_db)
    finally:
        temp_finance.unlink(missing_ok=True)
        temp_rag.unlink(missing_ok=True)

    finance_summary["path"] = str(finance_db)
    rag_summary["path"] = str(rag_db)
    return {
        "status": "PASS",
        "notice": "All values and narrative text are synthetic demo content, not actual company disclosures.",
        "finance": finance_summary,
        "rag": rag_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--finance-schema", type=Path, default=PROJECT_ROOT / "db" / "schema.sql")
    parser.add_argument("--rag-schema", type=Path, default=PROJECT_ROOT / "db" / "rag_schema.sql")
    parser.add_argument("--dimension", type=int, default=256)
    parser.add_argument("--force", action="store_true", help="显式覆盖 data-dir 中已有的两个 SQLite 数据库")
    args = parser.parse_args()
    try:
        result = initialize_demo_data(
            args.data_dir,
            finance_schema=args.finance_schema,
            rag_schema=args.rag_schema,
            force=args.force,
            dimension=args.dimension,
        )
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        parser.exit(2, f"初始化失败: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
