"""Extract a small, auditable set of annual-report financial candidates."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def number(value: str) -> float:
    return float(value.replace(",", ""))


def extract_candidates(pdf_path: Path, year: int) -> list[dict]:
    reader = PdfReader(str(pdf_path))
    target_page = None
    target_text = ""
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if "主要会计数据和财务指标" in normalize(text):
            target_page = page_number
            target_text = re.sub(r"\s+", " ", text).strip()
            break
    if target_page is None:
        raise ValueError(f"未找到主要会计数据和财务指标: {pdf_path}")

    patterns = {
        "revenue": (r"营业收入（元）\s*([\d,]+(?:\.\d+)?)", "营业收入", "元", "万元"),
        "net_profit_attributable": (
            r"归属于上市公司股东\s*的净利润（元）\s*([\d,]+(?:\.\d+)?)",
            "归属于上市公司股东的净利润",
            "元",
            "万元",
        ),
        "roe": (r"加权平均净资产收益\s*率\s*([\d,]+(?:\.\d+)?)%", "加权平均净资产收益率", "%", "%"),
    }
    result = []
    for metric_code, (pattern, label, raw_unit, normalized_unit) in patterns.items():
        match = re.search(pattern, target_text)
        if not match:
            raise ValueError(f"未找到指标 {metric_code}: {pdf_path}")
        raw_value = number(match.group(1))
        normalized_value = raw_value / 10000 if raw_unit == "元" else raw_value
        result.append(
            {
                "company_name": "凯莱英医药集团（天津）股份有限公司",
                "stock_code": "002821",
                "report_year": year,
                "report_quarter": 4,
                "period_code": "FY",
                "metric_code": metric_code,
                "metric_name": label,
                "raw_value": raw_value,
                "raw_unit": raw_unit,
                "normalized_value": round(normalized_value, 6),
                "normalized_unit": normalized_unit,
                "source_file": pdf_path.name,
                "source_page": target_page,
                "extraction_method": "pdf_text_regex",
                "quality_status": "candidate_pending_review",
            }
        )
    return result


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    records: list[dict] = []
    for item in manifest["items"]:
        if item["type"] != "financial_report" or "年度报告" not in item["file"]:
            continue
        year_match = re.search(r"(20\d{2})年年度报告", item["file"])
        if not year_match:
            raise ValueError(f"无法从文件名识别年份: {item['file']}")
        records.extend(extract_candidates(Path(item["source_path"]), int(year_match.group(1))))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"提取完成：{len(records)} 条候选事实")
    print(f"输出文件：{args.output.resolve()}")
    for record in records:
        print(
            f"{record['report_year']} {record['metric_code']}="
            f"{record['normalized_value']} {record['normalized_unit']} "
            f"(原始 {record['raw_value']} {record['raw_unit']}, 第{record['source_page']}页)"
        )


if __name__ == "__main__":
    main()

