"""Extract a compact, auditable MVP dataset from financial-report PDFs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

TARGETS = {
    "凯莱英": {"company_name": "凯莱英医药集团（天津）股份有限公司", "stock_code": "002821"},
    "百普赛斯": {"company_name": "北京百普赛斯生物科技股份有限公司", "stock_code": "301080"},
    "迈普医学": {"company_name": "迈普医学股份有限公司", "stock_code": "301033"},
    "百诚医药": {"company_name": "杭州百诚医药科技股份有限公司", "stock_code": "301096"},
    "泰格医药": {"company_name": "杭州泰格医药科技股份有限公司", "stock_code": "300347"},
    "迪安诊断": {"company_name": "迪安诊断技术集团股份有限公司", "stock_code": "300244"},
    "603127": {"company_name": "北京昭衍新药研究中心股份有限公司", "stock_code": "603127"},
    "603259": {"company_name": "无锡药明康德新药开发股份有限公司", "stock_code": "603259"},
    "688222": {"company_name": "成都先导药物开发股份有限公司", "stock_code": "688222"},
    "688276": {"company_name": "长春百克生物科技股份公司", "stock_code": "688276"},
}
METRICS = {
    "revenue": {"aliases": ["营业收入"], "name": "营业收入", "raw_unit": "元", "unit": "万元"},
    "net_profit_attributable": {
        "aliases": ["归属于上市公司股东的净利润"],
        "name": "归属于上市公司股东的净利润",
        "raw_unit": "元",
        "unit": "万元",
    },
    "net_profit_excl_non_recurring": {
        "aliases": [
            "归属于上市公司股东的扣除非经常性损益的净利润",
            "归属于上市公司股东的扣除非经常性损益的净利润",
        ],
        "name": "归属于上市公司股东的扣除非经常性损益的净利润",
        "raw_unit": "元",
        "unit": "万元",
    },
    "operating_cash_flow": {
        "aliases": ["经营活动产生的现金流量净额", "经营活动产生的现金流"],
        "name": "经营活动产生的现金流量净额",
        "raw_unit": "元",
        "unit": "万元",
    },
    "eps": {
        "aliases": ["基本每股收益"],
        "name": "基本每股收益",
        "raw_unit": "元/股",
        "unit": "元/股",
    },
    "roe": {
        "aliases": ["加权平均净资产收益率"],
        "name": "加权平均净资产收益率",
        "raw_unit": "%",
        "unit": "%",
    },
    "total_assets": {
        "aliases": ["总资产", "资产总额"],
        "name": "总资产",
        "raw_unit": "元",
        "unit": "万元",
    },
    "net_assets": {
        "aliases": ["归属于上市公司股东的净资产", "归属于上市公司股东的所有者权益"],
        "name": "归属于上市公司股东的净资产",
        "raw_unit": "元",
        "unit": "万元",
    },
}


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def spaced(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def label_pattern(label: str) -> str:
    # PDF extraction may place spaces/newlines between Chinese characters.
    return r"\s*".join(re.escape(ch) for ch in label)


def find_match(text: str, aliases: list[str]):
    matches = []
    for alias in aliases:
        m = re.search(label_pattern(alias), text)
        if m:
            matches.append((m.start(), m.end(), alias))
    return min(matches, default=None)


def value_tokens(text: str, percent: bool) -> list[str]:
    tokens = re.findall(r"[-−]?\d[\d,]*(?:\.\d+)?%?|—", text)
    out = []
    for token in tokens:
        if token == "—":
            continue
        if token.endswith("%") == percent:
            out.append(token[:-1] if token.endswith("%") else token)
    return out


def to_float(token: str) -> float:
    return float(token.replace(",", "").replace("−", "-"))


def pages_with_summary(page_texts: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [
        (n, raw)
        for n, raw in page_texts
        if "主要会计数据" in compact(raw) or "主要财务数据" in compact(raw)
    ]


def row_values(
    raw: str, metric_code: str, aliases: list[str], *, q3: bool
) -> tuple[list[str], str]:
    text = spaced(raw)
    match = find_match(text, aliases)
    if not match:
        raise ValueError(f"未找到指标标签: {aliases[0]}")
    # Stop at the next known metric label. This prevents the next table row
    # from being mistaken for a missing fourth annual column.
    next_starts = []
    for other_code, other_info in METRICS.items():
        for alias in other_info["aliases"]:
            if other_code == metric_code and alias == match[2]:
                continue
            other_match = re.search(label_pattern(alias), text[match[1] + 1 :])
            if other_match:
                next_starts.append(match[1] + 1 + other_match.start())
    stop = min(next_starts, default=match[1] + 180)
    window = text[match[1] : stop]
    info = METRICS[metric_code]
    percent = info["raw_unit"] == "%"
    values = value_tokens(window, percent=percent)
    if percent and not values:
        values = value_tokens(window, percent=False)
    return values, window


def extract_metric(
    page_texts: list[tuple[int, str]], summary: list[tuple[int, str]], metric_code: str, *, q3: bool
) -> tuple[float, int]:
    info = METRICS[metric_code]
    summary_numbers = {x[0] for x in summary}
    candidates = summary + [(n, raw) for n, raw in page_texts if n not in summary_numbers]
    last_error = None
    for page_number, raw in candidates:
        try:
            values, window = row_values(raw, metric_code, info["aliases"], q3=q3)
            if not values:
                raise ValueError("没有数值")
            if q3:
                # Balance rows are point-in-time: current end, prior end, change.
                # Income rows are current quarter, change, YTD, change.
                if metric_code in {"total_assets", "net_assets"}:
                    idx = 0
                elif metric_code == "operating_cash_flow" and ("不适用" in window or "—" in window):
                    idx = 0
                elif len(values) >= 3:
                    idx = 2
                else:
                    idx = 1 if len(values) >= 2 else 0
            else:
                # Annual columns: current, prior, change, two-years-ago.
                idx = 3 if len(values) >= 4 else (2 if len(values) >= 3 else 0)
            return to_float(values[idx]), page_number
        except Exception as exc:
            last_error = exc
    raise ValueError(str(last_error) if last_error else "未找到可解析值")


def record(
    meta: dict,
    period: str,
    year: int,
    quarter: int,
    code: str,
    raw_value: float,
    source: Path,
    page: int,
    method: str,
) -> dict:
    info = METRICS[code]
    norm = raw_value / 10000 if info["raw_unit"] == "元" else raw_value
    return {
        "company_name": meta["company_name"],
        "stock_code": meta["stock_code"],
        "report_year": year,
        "report_quarter": quarter,
        "period_code": period,
        "metric_code": code,
        "metric_name": info["name"],
        "raw_value": raw_value,
        "raw_unit": info["raw_unit"],
        "normalized_value": round(norm, 6),
        "normalized_unit": info["unit"],
        "source_file": source.name,
        "source_page": page,
        "extraction_method": method,
        "quality_status": "candidate_pending_review",
    }


def extract_doc(path: Path, meta: dict, *, q3: bool) -> list[dict]:
    reader = PdfReader(str(path))
    page_texts = [(n, page.extract_text() or "") for n, page in enumerate(reader.pages[:30], 1)]
    summary = pages_with_summary(page_texts)
    if not summary:
        raise ValueError("未找到主要会计数据页")
    out = []
    if q3:
        for code in METRICS:
            value, page = extract_metric(page_texts, summary, code, q3=True)
            out.append(
                record(
                    meta, "2025Q3", 2025, 3, code, value, path, page, "pdf_text_regex_summary_table"
                )
            )
    else:
        for code in METRICS:
            value, page = extract_metric(page_texts, summary, code, q3=False)
            # 2024 annual report comparable columns are 2024/2023/2022.
            for year, idx in ((2024, 0), (2023, 1), (2022, 2)):
                values, _ = row_values(
                    dict(page_texts)[page], code, METRICS[code]["aliases"], q3=False
                )
                # If the row has a no-percent change column, its fourth token
                # is the two-years-ago number; if change has %, third is it.
                actual_idx = [0, 1, 3][idx] if len(values) >= 4 else idx
                out.append(
                    record(
                        meta,
                        "FY",
                        year,
                        4,
                        code,
                        to_float(values[actual_idx]),
                        path,
                        page,
                        "pdf_text_regex_summary_table",
                    )
                )
    return out


def first_page(path: Path) -> str:
    return compact(PdfReader(str(path)).pages[0].extract_text() or "")


def choose(root: Path, q3: bool) -> dict[str, Path]:
    out = {}
    report_root = root / "附件2：财务报告"
    for path in report_root.rglob("*.pdf"):
        name = path.name
        if name.startswith(("603127_", "603259_", "688222_", "688276_")):
            key = name.split("_", 1)[0]
            text = first_page(path)
            wanted = "2025年第三季度报告" if q3 else "2024年年度报告"
            if wanted in text and "摘要" not in text:
                out[key] = path
        else:
            key = name.split("：", 1)[0]
            if key not in TARGETS:
                continue
            wanted = "2025年三季度报告.pdf" if q3 else "2024年年度报告.pdf"
            if name.endswith(wanted):
                out[key] = path
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, default=Path("资料待放入"))
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument(
        "--include-q3",
        action="store_true",
        help="显式扩展到2025年三季度；默认只读取10份2024年年度报告",
    )
    args = ap.parse_args()
    formal = args.data_root / "正式数据"
    annual = choose(formal, False)
    q3 = choose(formal, True) if args.include_q3 else {}
    rows, errors = [], []
    for key, path in sorted(annual.items()):
        try:
            rows.extend(extract_doc(path, TARGETS[key], q3=False))
        except Exception as exc:
            errors.append({"scope": "annual", "key": key, "file": str(path), "error": str(exc)})
    for key, path in sorted(q3.items()):
        try:
            rows.extend(extract_doc(path, TARGETS[key], q3=True))
        except Exception as exc:
            errors.append({"scope": "2025Q3", "key": key, "file": str(path), "error": str(exc)})
    # Add deterministic metrics needed by the analysis/chart tool.
    grouped = {}
    for r in rows:
        grouped.setdefault((r["stock_code"], r["period_code"], r["report_year"]), {})[
            r["metric_code"]
        ] = r
    for group in grouped.values():
        rev, profit, ocf = (
            group.get("revenue"),
            group.get("net_profit_attributable"),
            group.get("operating_cash_flow"),
        )
        if rev and profit and rev["normalized_value"]:
            ratio = profit["normalized_value"] / rev["normalized_value"] * 100
            rows.append(
                {
                    **rev,
                    "metric_code": "net_margin",
                    "metric_name": "净利率（计算）",
                    "raw_value": ratio,
                    "raw_unit": "%",
                    "normalized_value": round(ratio, 6),
                    "normalized_unit": "%",
                    "extraction_method": "python_formula",
                    "quality_status": "derived_pending_review",
                }
            )
        if rev and ocf and rev["normalized_value"]:
            ratio = ocf["normalized_value"] / rev["normalized_value"] * 100
            rows.append(
                {
                    **rev,
                    "metric_code": "operating_cash_margin",
                    "metric_name": "经营现金流/营业收入（计算）",
                    "raw_value": ratio,
                    "raw_unit": "%",
                    "normalized_value": round(ratio, 6),
                    "normalized_unit": "%",
                    "extraction_method": "python_formula",
                    "quality_status": "derived_pending_review",
                }
            )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "mvp_financial_candidates.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    audit = {
        "scope": "10份非摘要年度报告（每家公司1份2024年度报告，表内覆盖2022-2024）"
        + (" + 10份2025Q3报告" if args.include_q3 else ""),
        "annual_documents_selected": {k: str(v) for k, v in sorted(annual.items())},
        "q3_documents_selected": {k: str(v) for k, v in sorted(q3.items())},
        "target_company_count": 10,
        "annual_company_count": len(annual),
        "q3_company_count": len(q3),
        "record_count": len(rows),
        "unique_fact_count": len(
            {(r["stock_code"], r["period_code"], r["report_year"], r["metric_code"]) for r in rows}
        ),
        "errors": errors,
        "required_coverage": {
            "annual_years": [2022, 2023, 2024],
            "q3_period": "2025Q3" if args.include_q3 else None,
            "raw_metrics": list(METRICS),
            "derived_metrics": ["net_margin", "operating_cash_margin"],
        },
    }
    audit_path = args.output_dir / "mvp_financial_extraction_audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "csv": str(csv_path.resolve()),
                "audit": str(audit_path.resolve()),
                "annual_companies": len(annual),
                "q3_companies": len(q3),
                "records": len(rows),
                "errors": len(errors),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
