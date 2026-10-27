"""Audit chart-task evidence and PNG artifacts without emitting private content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

METRIC_UNITS = {
    "revenue": "万元",
    "net_profit_attributable": "万元",
    "net_profit_excl_non_recurring": "万元",
    "operating_cash_flow": "万元",
    "eps": "元/股",
    "roe": "%",
    "total_assets": "万元",
    "net_assets": "万元",
    "net_margin": "%",
    "operating_cash_margin": "%",
}
EXPECTED_TOOLS = ["financial_query", "financial_analysis", "chart_generation"]
EXPECTED_YEARS = [2022, 2023, 2024]


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        case_id = item.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"evidence line {line_number} has no valid id")
        if case_id in records:
            raise ValueError(f"duplicate evidence id: {case_id}")
        records[case_id] = item
    return records


def _metric_suffix(path: Path, stock_code: str, metric: str) -> bool:
    return path.name.endswith(f"_{stock_code}_{metric}.png")


def resolve_chart_path(value: str, artifact_dir: Path, stock_code: str, metric: str) -> Path | None:
    """Resolve evidence paths while refusing files outside the artifact directory."""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = artifact_dir / candidate.name
    try:
        resolved = candidate.resolve()
        artifact_root = artifact_dir.resolve()
        resolved.relative_to(artifact_root)
    except (OSError, ValueError):
        return None
    return resolved if _metric_suffix(resolved, stock_code, metric) else None


def inspect_png(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "png_status": "ERROR",
        "dimensions": None,
        "nonwhite_fraction": 0.0,
        "edge_touch": False,
    }
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            background = Image.new("RGB", rgb.size, "white")
            bbox = ImageChops.difference(rgb, background).getbbox()
            pixels = rgb.load()
            nonwhite = sum(
                pixels[x, y] != (255, 255, 255) for y in range(height) for x in range(width)
            )
            result.update(
                {
                    "png_status": "PASS" if bbox else "BLANK",
                    "dimensions": [width, height],
                    "nonwhite_fraction": round(nonwhite / (width * height), 6)
                    if width and height
                    else 0.0,
                    "edge_touch": bool(
                        bbox
                        and (bbox[0] == 0 or bbox[1] == 0 or bbox[2] >= width or bbox[3] >= height)
                    ),
                }
            )
    except (OSError, ValueError):
        pass
    return result


def audit_case(
    case: dict[str, Any], evidence: dict[str, Any], artifact_dir: Path
) -> dict[str, Any]:
    expected_metrics = case.get("expected_metrics") or []
    metric = expected_metrics[0] if len(expected_metrics) == 1 else ""
    response = evidence.get("response") or {}
    tools = [event.get("tool_name") for event in response.get("tool_events") or []]
    charts = response.get("charts") or []
    stock_code = str(case.get("expected_company") or "")
    findings: list[str] = []

    if response.get("status") != "success":
        findings.append("response_status_not_success")
    if tools != EXPECTED_TOOLS:
        findings.append("tool_chain_mismatch")
    if len(charts) < int(case.get("min_charts") or 0):
        findings.append("chart_count_below_minimum")
    if len(charts) != 1:
        findings.append("expected_one_chart")
    if not metric or metric not in METRIC_UNITS:
        findings.append("unsupported_metric_contract")

    resolved_paths = [
        resolve_chart_path(str(value), artifact_dir, stock_code, metric) for value in charts
    ]
    matching_paths = [path for path in resolved_paths if path is not None]
    if len(matching_paths) != 1:
        findings.append("expected_company_or_metric_not_in_chart_path")

    png = (
        inspect_png(matching_paths[0])
        if len(matching_paths) == 1
        else {
            "png_status": "MISSING",
            "dimensions": None,
            "nonwhite_fraction": 0.0,
            "edge_touch": False,
        }
    )
    if png["png_status"] != "PASS":
        findings.append(f"png_{str(png['png_status']).lower()}")
    if png["edge_touch"]:
        findings.append("low_risk_edge_margin_review")

    years = ((response.get("intent") or {}).get("period") or {}).get("years") or []
    if years != EXPECTED_YEARS:
        findings.append("year_axis_contract_mismatch")
    result_status = (
        "PASS"
        if not [item for item in findings if item != "low_risk_edge_margin_review"]
        else "FAIL"
    )
    return {
        "id": case.get("id", ""),
        "expected_company": stock_code,
        "expected_metric": metric,
        "expected_year_count": len(years),
        "expected_years": EXPECTED_YEARS,
        "expected_unit": METRIC_UNITS.get(metric, ""),
        "response_status": response.get("status", ""),
        "tool_chain": tools,
        "chart_count": len(charts),
        "png": png,
        "status": result_status,
        "findings": findings,
    }


def audit(dataset_path: Path, evidence_path: Path, artifact_dir: Path) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    cases = [case for case in dataset if str(case.get("id", "")).startswith("chart_")]
    evidence = read_jsonl(evidence_path)
    results: list[dict[str, Any]] = []
    for case in cases:
        item = evidence.get(case["id"])
        if item is None:
            results.append({"id": case["id"], "status": "FAIL", "findings": ["evidence_missing"]})
            continue
        results.append(audit_case(case, item, artifact_dir))
    failures = [item for item in results if item["status"] == "FAIL"]
    return {
        "privacy": "summary only; no question, answer, citation text, reviewer data, or raw trace is emitted",
        "cases": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "low_risk_warnings": sum(
            "low_risk_edge_margin_review" in item.get("findings", []) for item in results
        ),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(".demo-data/evaluation/dataset_extended_draft.json"),
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path(".demo-data/evaluation/human_review_demo.evidence.jsonl"),
    )
    parser.add_argument("--artifacts", type=Path, default=Path(".demo-data/artifacts"))
    parser.add_argument(
        "--output", type=Path, default=Path(".demo-data/evaluation/chart_audit.json")
    )
    args = parser.parse_args()
    result = audit(args.dataset, args.evidence, args.artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
