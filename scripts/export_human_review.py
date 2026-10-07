from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any



REVIEW_FIELDS = [
    "intent_correct",
    "tool_correct",
    "numeric_correct",
    "citation_relevant_1_to_5",
    "citation_supports_claim",
    "chart_correct",
    "answer_faithfulness_1_to_5",
    "answer_completeness_1_to_5",
    "question_naturalness_1_to_5",
    "review_status",
    "reviewer",
    "review_notes",
]


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def portable_paths(paths: list[str]) -> list[str]:
    """Keep exported evidence portable and avoid leaking local absolute paths."""
    root = Path.cwd().resolve()
    portable: list[str] = []
    for value in paths:
        path = Path(value)
        try:
            portable.append(path.resolve().relative_to(root).as_posix())
        except (OSError, ValueError):
            portable.append(path.name)
    return portable


def prepare_rows(
    dataset: list[dict[str, Any]],
    report: dict[str, Any] | None,
    *,
    run_agent: bool,
    use_llm: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    automatic = {row["id"]: row for row in (report or {}).get("results", [])}
    if run_agent:
        from finance_insight.agent import FinanceInsightAgent

        agent = FinanceInsightAgent()
    else:
        agent = None
    rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for case in dataset:
        auto = automatic.get(case["id"], {})
        result = agent.run(case["question"], use_llm=use_llm) if agent else None
        actual_intent = result.intent.model_dump(mode="json") if result and result.intent else None
        actual_tools = (
            [event.get("tool_name", "") for event in result.tool_events]
            if result
            else auto.get("actual_tools", [])
        )
        citations = result.citations if result else []
        charts = portable_paths(result.charts) if result else []

        row = {
            "id": case["id"],
            "category": case.get("category", ""),
            "label_status": case.get("label_status", ""),
            "question": case["question"],
            "expected_company": case.get("expected_company", ""),
            "expected_metrics": compact_json(case.get("expected_metrics", [])),
            "expected_tools": compact_json(case.get("expected_tools", [])),
            "expected_numeric": compact_json(case.get("expected_numeric")),
            "min_citations": case.get("min_citations", 0),
            "min_charts": case.get("min_charts", 0),
            "auto_task_success": auto.get("task_success", ""),
            "auto_company_ok": auto.get("company_ok", ""),
            "auto_metric_ok": auto.get("metric_ok", ""),
            "auto_tool_ok": auto.get("tool_selection_ok", ""),
            "auto_numeric_ok": auto.get("numeric_exact_match", ""),
            "actual_intent": compact_json(actual_intent),
            "actual_tools": compact_json(actual_tools),
            "actual_answer": result.answer if result else "",
            "actual_citations": compact_json(citations),
            "actual_charts": compact_json(charts),
            "actual_status": result.status if result else auto.get("status", ""),
            "fallback_used": result.fallback_used if result else "",
        }
        row.update({field: "" for field in REVIEW_FIELDS})
        rows.append(row)

        if result:
            response = result.model_dump(mode="json")
            response["charts"] = charts
            evidence.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "response": response,
                }
            )

    return rows, evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 60 条评测问题的人工审核表")
    parser.add_argument("--dataset", type=Path, default=Path("evals/dataset_extended_draft.json"))
    parser.add_argument("--report", type=Path, default=Path("data/evaluation/report_extended_draft.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/human_review_round1.csv"))
    parser.add_argument(
        "--run-agent",
        action="store_true",
        help="逐条运行 Agent，并把答案、引用、图表写入 CSV 和 evidence JSONL",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="与 --run-agent 一起使用真实 LLM；不指定时使用确定性 fallback",
    )
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8-sig"))
    report = json.loads(args.report.read_text(encoding="utf-8-sig")) if args.report.exists() else None
    rows, evidence = prepare_rows(dataset, report, run_agent=args.run_agent, use_llm=args.use_llm)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    if evidence:
        evidence_path = args.output.with_suffix(".evidence.jsonl")
        with evidence_path.open("w", encoding="utf-8") as stream:
            for item in evidence:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Agent evidence: {evidence_path} ({len(evidence)} cases)")

    print(f"Human review sheet: {args.output} ({len(rows)} cases)")


if __name__ == "__main__":
    main()


