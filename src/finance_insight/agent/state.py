from __future__ import annotations

from typing import Any, TypedDict

from finance_insight.schemas import QueryIntent, TaskPlan, ValidationReport


class AgentState(TypedDict, total=False):
    question: str
    trace_id: str
    session_id: str
    use_llm: bool
    intent: QueryIntent | None
    clarification_reason: str
    task_plan: TaskPlan
    financial_data: list[dict[str, Any]]
    calculations: dict[str, Any]
    anomalies: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    rag_chunks: list[dict[str, Any]]
    chart_paths: list[str]
    tool_events: list[dict[str, Any]]
    errors: list[str]
    final_answer: str
    fallback_used: bool
    step_count: int
    evidence_summary: dict[str, Any]
    validation: ValidationReport | None
