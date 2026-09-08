"""Validate and, only when complete, freeze the private human review sheet."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "intent_correct", "tool_correct", "numeric_correct",
    "citation_relevant_1_to_5", "citation_supports_claim", "chart_correct",
    "answer_faithfulness_1_to_5", "answer_completeness_1_to_5",
    "question_naturalness_1_to_5", "review_status", "reviewer", "review_notes",
}
VALID_STATUS = {"approved", "needs_revision", "rejected"}
TRI_STATE_FIELDS = {"intent_correct", "tool_correct", "numeric_correct", "citation_supports_claim", "chart_correct"}
SCORE_FIELDS = {"citation_relevant_1_to_5", "answer_faithfulness_1_to_5", "answer_completeness_1_to_5", "question_naturalness_1_to_5"}


def _value(row: dict[str, str], field: str) -> str:
    return (row.get(field) or "").strip()


def read_review_rows(path: Path) -> list[dict[str, str]]:
    """Read review sheets saved by UTF-8 tools or common Chinese spreadsheet apps."""
    content = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = content.decode(encoding)
            return list(csv.DictReader(text.splitlines()))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别审核表编码: {path}")


def validate_rows(rows: list[dict[str, str]], expected_count: int = 60) -> dict[str, Any]:
    errors: list[str] = []
    if len(rows) != expected_count:
        errors.append(f"expected {expected_count} rows, got {len(rows)}")
    ids = [_value(row, "id") for row in rows]
    if not all(ids) or len(set(ids)) != len(ids):
        errors.append("id must be non-empty and unique")
    if rows:
        missing = sorted(REQUIRED_FIELDS - set(rows[0]))
        if missing:
            errors.append(f"missing review fields: {','.join(missing)}")

    for index, row in enumerate(rows, start=2):
        for field in TRI_STATE_FIELDS:
            value = _value(row, field)
            if value not in {"0", "1", "NA"}:
                errors.append(f"row {index}: {field} must be 0, 1 or NA")
        for field in SCORE_FIELDS:
            value = _value(row, field)
            if value != "NA" and value not in {str(number) for number in range(1, 6)}:
                errors.append(f"row {index}: {field} must be 1-5 or NA")
        status = _value(row, "review_status")
        if status not in VALID_STATUS:
            errors.append(f"row {index}: review_status must be approved, needs_revision or rejected")
        if not _value(row, "reviewer"):
            errors.append(f"row {index}: reviewer is required")
        if not _value(row, "review_notes"):
            errors.append(f"row {index}: review_notes is required")

    return {
        "valid": not errors,
        "rows": len(rows),
        "reviewed_rows": sum(bool(_value(row, "review_status")) for row in rows),
        "status_counts": dict(Counter(_value(row, "review_status") or "unreviewed" for row in rows)),
        "reviewers": sorted({_value(row, "reviewer") for row in rows if _value(row, "reviewer")}),
        "errors": errors[:20],
    }


def freeze_dataset(dataset_path: Path, review_path: Path, output_path: Path, reviewer: str | None) -> dict[str, Any]:
    review_rows = read_review_rows(review_path)
    validation = validate_rows(review_rows)
    if not validation["valid"]:
        return {"status": "BLOCKED", "reason": "human review is incomplete or invalid", "validation": validation}

    dataset = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    by_id = {row["id"]: row for row in review_rows}
    if {case["id"] for case in dataset} != set(by_id):
        return {"status": "BLOCKED", "reason": "review ids do not match dataset", "validation": validation}
    frozen: list[dict[str, Any]] = []
    for case in dataset:
        review = by_id[case["id"]]
        item = dict(case)
        item["label_status"] = "human_reviewed_v1"
        item["human_review"] = {
            field: _value(review, field)
            for field in sorted(REQUIRED_FIELDS)
        }
        item["reviewed_at"] = date.today().isoformat()
        item["reviewer"] = reviewer or _value(review, "reviewer")
        frozen.append(item)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "FROZEN", "output": str(output_path), "cases": len(frozen), "validation": validation}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=Path("evals/human_review_round1.csv"))
    parser.add_argument("--dataset", type=Path, default=Path("evals/dataset_extended_draft.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/dataset_human_reviewed_v1.json"))
    parser.add_argument("--reviewer", help="override reviewer metadata in the frozen dataset")
    args = parser.parse_args()
    if not args.review.exists():
        result = {"status": "BLOCKED", "reason": f"review sheet missing: {args.review}"}
    else:
        result = freeze_dataset(args.dataset, args.review, args.output, args.reviewer)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "FROZEN":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
