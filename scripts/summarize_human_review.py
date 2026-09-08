"""Produce a privacy-safe aggregate for the 60-row human review workflow."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

try:
    from validate_human_review import SCORE_FIELDS, TRI_STATE_FIELDS, read_review_rows, validate_rows
except ModuleNotFoundError:
    import importlib.util
    import sys

    validator_path = Path(__file__).with_name("validate_human_review.py")
    validator_spec = importlib.util.spec_from_file_location("validate_human_review", validator_path)
    if not validator_spec or not validator_spec.loader:
        raise
    validator = importlib.util.module_from_spec(validator_spec)
    sys.modules["validate_human_review"] = validator
    validator_spec.loader.exec_module(validator)
    SCORE_FIELDS = validator.SCORE_FIELDS
    TRI_STATE_FIELDS = validator.TRI_STATE_FIELDS
    read_review_rows = validator.read_review_rows
    validate_rows = validator.validate_rows


def _value(row: dict[str, str], field: str) -> str:
    return (row.get(field) or "").strip()


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    validation = validate_rows(rows)
    status_counts = Counter(_value(row, "review_status") or "unreviewed" for row in rows)
    categories: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        categories[_value(row, "category") or "uncategorized"].append(row)

    def rate(items: list[dict[str, str]], field: str) -> float | None:
        values = [_value(row, field) for row in items if _value(row, field) in {"0", "1"}]
        return round(mean(value == "1" for value in values), 4) if values else None

    def score(items: list[dict[str, str]], field: str) -> float | None:
        values = [int(_value(row, field)) for row in items if _value(row, field).isdigit()]
        return round(mean(values), 3) if values else None

    all_metrics = {
        **{f"{field}_rate": rate(rows, field) for field in sorted(TRI_STATE_FIELDS)},
        **{f"{field}_mean": score(rows, field) for field in sorted(SCORE_FIELDS)},
    }
    return {
        "status": "READY_TO_FREEZE" if validation["valid"] else "INCOMPLETE",
        "privacy": "aggregate only; no question, answer, citation, reviewer name, or note is emitted",
        "review_rows": len(rows),
        "review_status_counts": dict(status_counts),
        "reviewed_rows": len(rows) - status_counts["unreviewed"],
        "metrics": all_metrics,
        "category_summary": {
            category: {
                "cases": len(items),
                "approved_rate": round(
                    sum(_value(row, "review_status") == "approved" for row in items) / len(items), 4
                ) if items else 0,
                "numeric_correct_rate": rate(items, "numeric_correct"),
                "citation_supports_claim_rate": rate(items, "citation_supports_claim"),
                "answer_faithfulness_mean": score(items, "answer_faithfulness_1_to_5"),
            }
            for category, items in sorted(categories.items())
        },
        "validation": {
            "valid": validation["valid"],
            "errors": validation["errors"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=Path("evals/human_review_round1.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/human_review_summary.json"))
    args = parser.parse_args()
    result = summarize(read_review_rows(args.review))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "READY_TO_FREEZE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
