"""Validate the Phase 1 MVP candidate dataset without loading source PDFs into the chat."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

RAW = [
    "revenue",
    "net_profit_attributable",
    "net_profit_excl_non_recurring",
    "operating_cash_flow",
    "eps",
    "roe",
    "total_assets",
    "net_assets",
]
DERIVED = ["net_margin", "operating_cash_margin"]
EXPECTED_STOCKS = 10


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument(
        "--require-q3",
        action="store_true",
        help="同时要求数据包含 2025Q3；默认只校验 FY 2022—FY 2024。",
    )
    args = ap.parse_args()
    df = pd.read_csv(args.csv, dtype={"stock_code": str})
    errors: list[str] = []
    expected_periods = {("FY", 2022), ("FY", 2023), ("FY", 2024)}
    if args.require_q3:
        expected_periods.add(("2025Q3", 2025))
    actual_periods = set(zip(df.period_code, df.report_year, strict=False))
    if df.stock_code.nunique() != EXPECTED_STOCKS:
        errors.append(f"公司数={df.stock_code.nunique()}，预期={EXPECTED_STOCKS}")
    if actual_periods != expected_periods:
        errors.append(f"期间集合不一致: actual={sorted(actual_periods)}")
    expected_codes = set(RAW + DERIVED)
    if set(df.metric_code) != expected_codes:
        errors.append(f"指标集合不一致: actual={sorted(set(df.metric_code))}")
    counts = df.groupby(["stock_code", "period_code", "report_year", "metric_code"]).size()
    duplicates = counts[counts != 1]
    if not duplicates.empty:
        errors.append(f"事实键非一行: {len(duplicates)} 个")
    if not df.normalized_value.map(math.isfinite).all():
        errors.append("存在非有限数值")
    for metric in ["revenue", "total_assets", "net_assets"]:
        bad = df[(df.metric_code == metric) & (df.normalized_value <= 0)]
        if not bad.empty:
            errors.append(f"{metric} 存在非正数: {len(bad)} 条")
    roe = df[df.metric_code == "roe"]
    if (roe.normalized_value.abs() > 1000).any():
        errors.append("ROE 超出合理审计阈值 ±1000%")
    # Verify derived values against raw facts.
    facts = df.pivot_table(
        index=["stock_code", "period_code", "report_year"],
        columns="metric_code",
        values="normalized_value",
    )
    for idx, row in facts.iterrows():
        if row.revenue == 0:
            errors.append(f"收入为0，无法校验衍生指标: {idx}")
            continue
        for code, expected in [
            ("net_margin", row.net_profit_attributable / row.revenue * 100),
            ("operating_cash_margin", row.operating_cash_flow / row.revenue * 100),
        ]:
            if abs(row[code] - expected) > 1e-4:
                errors.append(f"{code} 公式不一致: {idx}")
    audit = {
        "input": str(args.csv.resolve()),
        "rows": int(len(df)),
        "companies": int(df.stock_code.nunique()),
        "periods": sorted([list(x) for x in actual_periods]),
        "metrics": sorted(set(df.metric_code)),
        "raw_fact_rows": int(len(df[df.metric_code.isin(RAW)])),
        "derived_fact_rows": int(len(df[df.metric_code.isin(DERIVED)])),
        "errors": errors,
        "status": "READY_FOR_PHASE_2" if not errors else "BLOCKED",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "mvp_financial_validation.json"
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
