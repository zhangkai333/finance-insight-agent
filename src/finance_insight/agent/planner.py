from __future__ import annotations

import uuid
from typing import Literal

from finance_insight.schemas import QueryIntent, SubTask, TaskPlan


def _task(
    kind: Literal[
        "financial_query",
        "financial_analysis",
        "annual_report_search",
        "chart_generation",
        "validation",
        "clarification",
    ],
    objective: str,
    dependencies: list[str] | None = None,
) -> SubTask:
    return SubTask(
        id=f"task_{uuid.uuid4().hex[:8]}",
        kind=kind,
        objective=objective,
        dependencies=dependencies or [],
    )


def build_task_plan(question: str, intent: QueryIntent | None) -> TaskPlan:
    """Build a bounded, inspectable plan from policy-controlled intent flags.

    The planner does not produce executable SQL or arbitrary tools. It only
    selects the application's allowlisted operations and their dependencies.
    """
    if intent is None:
        clarification = "请补充公司、股票代码和需要查询的财务指标。"
        return TaskPlan(
            plan_id=f"plan_{uuid.uuid4().hex}",
            strategy="clarification",
            subtasks=[_task("clarification", clarification)],
            clarification_question=clarification,
            planner="deterministic-policy-v1",
        )

    multi_intent = (
        any(word in question for word in ("同时", "并且", "以及", "和", "分别"))
        and len(intent.metrics) > 1
    )
    has_fusion = intent.needs_rag and (intent.needs_calculation or len(intent.metrics) > 1)
    strategy = "multi_intent" if multi_intent else "fusion" if has_fusion else "single"
    subtasks: list[SubTask] = []
    query = _task("financial_query", "查询白名单结构化财务事实")
    subtasks.append(query)

    previous = [query.id]
    if intent.needs_calculation or intent.needs_anomaly_detection:
        calc = _task("financial_analysis", "使用 Python 计算同比、CAGR、趋势和异常", previous)
        subtasks.append(calc)
        previous = [calc.id]
    if intent.needs_rag:
        rag_objective = "检索原始财报/研报证据，解释指标变化并返回页码引用"
        if "为什么" in question or "原因" in question or "归因" in question:
            rag_objective = "检索导致指标变化的经营原因、风险或业务驱动因素"
        subtasks.append(_task("annual_report_search", rag_objective, previous))
        previous = [subtasks[-1].id]
    if intent.needs_chart:
        subtasks.append(_task("chart_generation", "基于已校验的分析序列生成趋势图", previous))
        previous = [subtasks[-1].id]
    subtasks.append(_task("validation", "校验数字、年份、指标、引用和工具结果的一致性", previous))
    clarification = clarification_needed(intent)
    if clarification:
        strategy = "clarification"
        subtasks = [_task("clarification", clarification)]
    return TaskPlan(
        plan_id=f"plan_{uuid.uuid4().hex}",
        strategy=strategy,
        subtasks=subtasks,
        clarification_question=clarification,
        planner="deterministic-policy-v1",
    )


def clarification_needed(intent: QueryIntent | None) -> str | None:
    if intent is None or intent.confidence >= 0.65:
        return None
    if not intent.companies:
        return "请补充需要分析的公司名称或股票代码。"
    if not intent.metrics:
        return "请补充需要查询的财务指标，例如营业收入、归母净利润或 ROE。"
    return "请补充公司、年份或指标范围，我再继续分析。"
