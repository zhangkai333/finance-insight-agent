from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from finance_insight.agent.planner import build_task_plan
from finance_insight.agent.state import AgentState
from finance_insight.agent.validator import validate_evidence
from finance_insight.config import Settings, settings
from finance_insight.intent_parser import parse_intent, parse_intent_with_llm
from finance_insight.llm import build_llm_client
from finance_insight.observability import JsonlTracer
from finance_insight.prompts import ANSWER_SYSTEM_PROMPT, PROMPT_VERSION
from finance_insight.resilience import retry_call
from finance_insight.schemas import QueryResponse, ToolResult
from finance_insight.tools import (
    AnnualReportSearchTool,
    ChartGenerationTool,
    FinancialAnalysisTool,
    FinancialQueryTool,
)


class FinanceInsightAgent:
    """有边界的财务分析工作流：LLM 不直接查库，也不直接计算数值。"""

    def __init__(self, config: Settings = settings):
        self.config = config
        self.sql = FinancialQueryTool(config)
        self.analysis = FinancialAnalysisTool()
        self.rag = AnnualReportSearchTool(config)
        self.chart = ChartGenerationTool(config)
        self.tracer = JsonlTracer(config.log_dir)
        self.llm = build_llm_client(config)

        graph = StateGraph(AgentState)
        graph.add_node("parse", self._parse)
        graph.add_node("planner", self._planner)
        graph.add_node("query_sql", self._query)
        graph.add_node("calculate", self._calculate)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("chart", self._chart)
        graph.add_node("validate", self._validate)
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge(START, "parse")
        graph.add_edge("parse", "planner")
        graph.add_conditional_edges(
            "planner",
            self._after_planner,
            {"query_sql": "query_sql", "validate": "validate"},
        )
        graph.add_conditional_edges(
            "query_sql",
            self._after_query,
            {"calculate": "calculate", "retrieve": "retrieve", "validate": "validate"},
        )
        graph.add_conditional_edges(
            "calculate",
            self._after_calculate,
            {"retrieve": "retrieve", "chart": "chart", "validate": "validate"},
        )
        graph.add_conditional_edges(
            "retrieve", self._after_retrieve, {"chart": "chart", "validate": "validate"}
        )
        graph.add_edge("chart", "validate")
        graph.add_edge("validate", "synthesize")
        graph.add_edge("synthesize", END)
        self.graph = graph.compile(checkpointer=MemorySaver())

    def _call_tool(self, operation: Callable[[], ToolResult]) -> ToolResult:
        result, attempts = retry_call(
            operation, attempts=2, retry_if=lambda item: item.status == "error"
        )
        result.data.setdefault("retry_attempts", attempts)
        return result

    def _event(self, state: AgentState, result: ToolResult) -> dict[str, Any]:
        event = {
            "tool_name": result.tool_name,
            "status": result.status,
            "latency_ms": round(result.latency_ms, 2),
            "error": result.error,
            "fallback_used": result.fallback_used,
            "retry_attempts": result.data.get("retry_attempts", 1),
            "details": {
                key: result.data[key]
                for key in (
                    "backend",
                    "requested_backend",
                    "record_count",
                    "scope",
                    "retrieval_mode",
                    "embedding_provider",
                    "fallback_reason",
                    "requested_rag_backend",
                    "effective_rag_backend",
                    "anomaly_count",
                    "count",
                    "connection_pool",
                    "reranker",
                    "retrieval_attempts",
                    "candidate_count",
                    "evidence_score",
                    "evidence_sufficient",
                    "cause_evidence_sufficient",
                )
                if key in result.data
            },
        }
        self.tracer.emit(
            trace_id=state["trace_id"],
            session_id=state["session_id"],
            event=result.tool_name,
            status=result.status,
            latency_ms=event["latency_ms"],
            error=result.error,
            retry_attempts=event["retry_attempts"],
        )
        return event

    def _parse(self, state: AgentState) -> dict[str, Any]:
        parse_fallback = not self.config.llm_enabled
        try:
            if state.get("use_llm", True) and self.config.llm_enabled:
                try:
                    intent = parse_intent_with_llm(state["question"], self.llm, self.config)
                    parse_fallback = False
                except Exception as exc:
                    intent = parse_intent(state["question"], self.config)
                    parse_fallback = True
                    self.tracer.emit(
                        trace_id=state["trace_id"],
                        session_id=state["session_id"],
                        event="structured_output_fallback",
                        status="partial",
                        error=str(exc),
                    )
            else:
                intent = parse_intent(state["question"], self.config)
        except ValueError as exc:
            previous = state.get("intent")
            if not previous:
                self.tracer.emit(
                    trace_id=state["trace_id"],
                    session_id=state["session_id"],
                    event="parse_intent",
                    status="partial",
                    error=str(exc),
                )
                return {
                    "intent": None,
                    "clarification_reason": str(exc),
                    "tool_events": [],
                    "errors": [],
                    "financial_data": [],
                    "calculations": {},
                    "anomalies": [],
                    "rag_chunks": [],
                    "chart_paths": [],
                    "citations": [],
                    "validation": None,
                    "final_answer": "",
                    "fallback_used": parse_fallback,
                    "step_count": 1,
                }
            contextual_question = f"{previous.companies[0].stock_code} {state['question']}"
            intent = parse_intent(contextual_question, self.config)
            intent.question = state["question"]
            intent.parser = "deterministic-rule-v1+session-context"
            parse_fallback = True
        self.tracer.emit(
            trace_id=state["trace_id"],
            session_id=state["session_id"],
            event="parse_intent",
            status="success",
            intent=intent.model_dump(),
            prompt_version=PROMPT_VERSION,
        )
        return {
            "intent": intent,
            "tool_events": [],
            "errors": [],
            "financial_data": [],
            "calculations": {},
            "anomalies": [],
            "rag_chunks": [],
            "chart_paths": [],
            "citations": [],
            "validation": None,
            "final_answer": "",
            "fallback_used": parse_fallback,
            "step_count": 1,
        }

    def _planner(self, state: AgentState) -> dict[str, Any]:
        plan = build_task_plan(state["question"], state.get("intent"))
        self.tracer.emit(
            trace_id=state["trace_id"],
            session_id=state["session_id"],
            event="plan_task",
            status="success",
            strategy=plan.strategy,
            subtask_count=len(plan.subtasks),
        )
        return {"task_plan": plan, "step_count": state.get("step_count", 0) + 1}

    def _query(self, state: AgentState) -> dict[str, Any]:
        result = self._call_tool(lambda: self.sql.run(state["intent"]))
        return {
            "financial_data": result.data.get("records", []),
            "tool_events": state.get("tool_events", []) + [self._event(state, result)],
            "errors": state.get("errors", []) + ([result.error] if result.error else []),
            "fallback_used": state.get("fallback_used", False) or result.fallback_used,
            "step_count": state.get("step_count", 0) + 1,
        }

    def _calculate(self, state: AgentState) -> dict[str, Any]:
        result = self._call_tool(
            lambda: self.analysis.run(
                state.get("financial_data", []),
                detect_anomalies=state["intent"].needs_anomaly_detection,
            )
        )
        return {
            "calculations": result.data,
            "anomalies": result.data.get("anomalies", []),
            "tool_events": state.get("tool_events", []) + [self._event(state, result)],
            "errors": state.get("errors", []) + ([result.error] if result.error else []),
            "fallback_used": state.get("fallback_used", False) or result.fallback_used,
            "step_count": state.get("step_count", 0) + 1,
        }

    def _retrieve(self, state: AgentState) -> dict[str, Any]:
        intent = state["intent"]
        metric_names = ", ".join(intent.metrics)
        search_query = (
            f"{state['question']} {metric_names} {' '.join(map(str, intent.period.years))}"
        )
        if state.get("anomalies"):
            search_query += " 主要原因 经营风险 业务驱动"
        result = self._call_tool(
            lambda: self.rag.run(
                intent,
                query=search_query,
                top_k=4,
            )
        )
        return {
            "rag_chunks": result.data.get("chunks", []),
            "citations": result.citations,
            "tool_events": state.get("tool_events", []) + [self._event(state, result)],
            "errors": state.get("errors", []) + ([result.error] if result.error else []),
            "fallback_used": state.get("fallback_used", False) or result.fallback_used,
            "step_count": state.get("step_count", 0) + 1,
        }

    def _validate(self, state: AgentState) -> dict[str, Any]:
        report = validate_evidence(
            state.get("intent"),
            state.get("financial_data", []),
            state.get("calculations", {}),
            state.get("citations", []),
            errors=state.get("errors", []),
        )
        self.tracer.emit(
            trace_id=state["trace_id"],
            session_id=state["session_id"],
            event="validate_evidence",
            status=report.status,
            warning_count=len(report.warnings),
        )
        return {"validation": report, "step_count": state.get("step_count", 0) + 1}

    def _chart(self, state: AgentState) -> dict[str, Any]:
        result = self._call_tool(
            lambda: self.chart.run(
                state.get("calculations", {}).get("series", []),
                trace_id=state["trace_id"],
            )
        )
        return {
            "chart_paths": result.data.get("chart_paths", []),
            "tool_events": state.get("tool_events", []) + [self._event(state, result)],
            "errors": state.get("errors", []) + ([result.error] if result.error else []),
            "fallback_used": state.get("fallback_used", False) or result.fallback_used,
            "step_count": state.get("step_count", 0) + 1,
        }

    def _after_planner(self, state: AgentState) -> str:
        return "validate" if state["task_plan"].strategy == "clarification" else "query_sql"

    def _after_query(self, state: AgentState) -> str:
        if not state.get("financial_data"):
            return "validate"
        if (
            state["intent"].needs_calculation
            or state["intent"].needs_anomaly_detection
            or state["intent"].needs_chart
        ):
            return "calculate"
        if state["intent"].needs_rag:
            return "retrieve"
        return "validate"

    def _after_calculate(self, state: AgentState) -> str:
        if state["intent"].needs_rag or bool(state.get("anomalies")):
            return "retrieve"
        if state["intent"].needs_chart:
            return "chart"
        return "validate"

    def _after_retrieve(self, state: AgentState) -> str:
        return "chart" if state["intent"].needs_chart else "validate"

    def _deterministic_answer(self, state: AgentState) -> str:
        plan = state.get("task_plan")
        if plan and plan.clarification_question:
            return f"需要补充信息：{plan.clarification_question}"
        if not state.get("financial_data"):
            return "查询失败：" + "；".join(state.get("errors", []) or ["没有匹配数据"])
        title = (
            "跨公司财务排名"
            if state["intent"].task_type == "ranking"
            else f"{state['intent'].companies[0].company_name} 财务分析"
        )
        lines = [f"## {title}", "", "### 结构化财务事实"]
        if state["intent"].task_type == "ranking":
            for row in state["financial_data"][:10]:
                lines.append(
                    f"- 第{row['rank']}名 {row['company_name']}：{float(row['metric_value']):,.2f}{row['normalized_unit']}"
                )
        elif state.get("calculations", {}).get("series"):
            for item in state["calculations"]["series"]:
                values = "；".join(
                    f"{p['year']}年 {p['value']:,.2f}{p['unit']}"
                    + (f"（同比 {p['yoy_pct']:+.2f}%）" if p.get("yoy_pct") is not None else "")
                    for p in item["points"]
                )
                cagr = (
                    f"，期间 CAGR {item['cagr_pct']:+.2f}%"
                    if item.get("cagr_pct") is not None
                    else ""
                )
                lines.append(f"- {item['metric_name']}：{values}{cagr}")
        else:
            for row in state["financial_data"][:20]:
                lines.append(
                    f"- {row['report_year']}年 {row['metric_name']}：{float(row['metric_value']):,.2f}{row['normalized_unit']}"
                )
        if state.get("anomalies"):
            lines.extend(["", "### 异常检测"])
            lines.extend(f"- {item['year']}年：{item['message']}" for item in state["anomalies"])
        if state.get("rag_chunks"):
            lines.extend(["", "### 年报依据"])
            for chunk in state["rag_chunks"][:4]:
                snippet = chunk.get("excerpt") or " ".join(chunk["content"].split())[:220]
                lines.append(f"- {snippet}……（{chunk['source_file']}，第{chunk['page_number']}页）")
        if state.get("chart_paths"):
            lines.extend(["", "### 图表", *[f"- {path}" for path in state["chart_paths"]]])
        validation = state.get("validation")
        if validation and validation.status != "passed":
            lines.extend(["", "### 校验提示"])
            lines.extend(f"- {warning}" for warning in validation.warnings)
            rag_event = next(
                (
                    event
                    for event in state.get("tool_events", [])
                    if event.get("tool_name") == "annual_report_search"
                ),
                None,
            )
            if rag_event and not rag_event.get("details", {}).get(
                "cause_evidence_sufficient", True
            ):
                lines.append(
                    "- 未检索到覆盖全部目标指标的明确原因原文；以上仅为可验证事实，不据此推断原因。"
                )
        lines.extend(
            [
                "",
                "> 说明：数值来自结构化财务事实库，变化率由 Python 计算，原因引用来自年报；本结果用于经营分析，不构成投资建议。",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _evidence_summary(state: AgentState) -> dict[str, Any]:
        """Expose bounded, typed evidence for the UI and replay checks."""
        facts = [
            {
                key: row.get(key)
                for key in (
                    "stock_code",
                    "company_name",
                    "report_year",
                    "metric_code",
                    "metric_name",
                    "metric_value",
                    "normalized_unit",
                    "source_file",
                    "source_page",
                    "quality_status",
                )
                if key in row
            }
            for row in state.get("financial_data", [])[:50]
        ]
        calculations = state.get("calculations", {})
        series = []
        for item in calculations.get("series", [])[:20]:
            series.append(
                {
                    "stock_code": item.get("stock_code"),
                    "company_name": item.get("company_name"),
                    "metric_code": item.get("metric_code"),
                    "metric_name": item.get("metric_name"),
                    "points": item.get("points", [])[:10],
                    "cagr_pct": item.get("cagr_pct"),
                }
            )
        return {
            "facts": facts,
            "calculations": {
                "series": series,
                "anomalies": state.get("anomalies", [])[:20],
                "rules": calculations.get("rules", {}),
            },
            "provenance": {
                "facts": "FinancialQueryTool / SQLite or MySQL",
                "calculations": "FinancialAnalysisTool / Python deterministic formulas",
                "citations": "AnnualReportSearchTool / FTS5 + vector or fallback",
                "summary": "LLM synthesis or deterministic fallback; never source of numeric facts",
            },
        }

    def _execution_context(self, state: AgentState) -> dict[str, Any]:
        """Return only the small set of run facts useful to a reviewer."""
        sql_event = next(
            (
                event
                for event in state.get("tool_events", [])
                if event.get("tool_name") == "financial_query"
            ),
            {},
        )
        details = sql_event.get("details", {})
        return {
            "requested_backend": details.get("requested_backend", self.config.finance_backend),
            "effective_backend": details.get("backend", self.config.finance_backend),
            "backend_fallback_reason": details.get("fallback_reason"),
            "llm_requested": bool(state.get("use_llm", True)),
            "llm_configured": self.config.llm_enabled,
            "fallback_used": bool(state.get("fallback_used", False)),
            "step_count": state.get("step_count", 0),
            "recursion_limit": 12,
        }

    @staticmethod
    def _response_status(state: AgentState) -> str:
        plan = state.get("task_plan")
        if plan and plan.strategy == "clarification":
            return "partial"
        validation = state.get("validation")
        if validation and validation.status == "failed":
            return (
                "error"
                if not state.get("financial_data") and not state.get("citations")
                else "partial"
            )
        if validation and validation.status == "warning":
            return "partial"
        if any(
            event.get("status") in {"partial", "error"} for event in state.get("tool_events", [])
        ):
            return "partial" if state.get("financial_data") or state.get("citations") else "error"
        if not state.get("errors") and (not validation or validation.status == "passed"):
            return "success"
        if state.get("financial_data") or state.get("citations"):
            return "partial"
        return "error"

    def _synthesize(self, state: AgentState) -> dict[str, Any]:
        answer = self._deterministic_answer(state)
        fallback = state.get("fallback_used", False)
        if state.get("use_llm", True) and self.config.llm_enabled:
            bounded_chunks = []
            for chunk in state.get("rag_chunks", [])[:4]:
                item = dict(chunk)
                item["content"] = " ".join(str(item.get("content", "")).split())[
                    : self.config.rag_chunk_max_chars_for_llm
                ]
                bounded_chunks.append(item)
            evidence = {
                "question": state["question"],
                "financial_data": state.get("financial_data", []),
                "calculations": state.get("calculations", {}),
                "rag_chunks": bounded_chunks,
                "task_plan": state.get("task_plan"),
                "validation": state.get("validation"),
            }
            try:
                answer = self.llm.chat(
                    [
                        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(evidence, ensure_ascii=False, default=str),
                        },
                    ]
                ).content
                fallback = False
            except Exception as exc:
                self.tracer.emit(
                    trace_id=state["trace_id"],
                    session_id=state["session_id"],
                    event="llm_fallback",
                    status="partial",
                    error=str(exc),
                )
                return {
                    "final_answer": answer,
                    "fallback_used": True,
                    "errors": state.get("errors", [])
                    + [f"LLM 调用失败，已降级为确定性报告: {exc}"],
                    "step_count": state.get("step_count", 0) + 1,
                }
        self.tracer.emit(
            trace_id=state["trace_id"],
            session_id=state["session_id"],
            event="synthesize",
            status="success",
            fallback_used=fallback,
        )
        return {
            "final_answer": answer,
            "fallback_used": fallback,
            "step_count": state.get("step_count", 0) + 1,
        }

    def run(
        self, question: str, *, session_id: str | None = None, use_llm: bool = True
    ) -> QueryResponse:
        session_id = session_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        initial: AgentState = {
            "question": question,
            "session_id": session_id,
            "trace_id": trace_id,
            "use_llm": use_llm,
            "tool_events": [],
            "errors": [],
            "step_count": 0,
        }
        try:
            final = self.graph.invoke(
                initial,
                config={"configurable": {"thread_id": session_id}, "recursion_limit": 12},
            )
            status = self._response_status(final)
            return QueryResponse(
                trace_id=trace_id,
                session_id=session_id,
                status=status,
                answer=final.get("final_answer", ""),
                intent=final.get("intent"),
                charts=final.get("chart_paths", []),
                citations=final.get("citations", []),
                tool_events=final.get("tool_events", []),
                errors=final.get("errors", []),
                fallback_used=final.get("fallback_used", False),
                evidence_summary=self._evidence_summary(final),
                execution_context=self._execution_context(final),
                task_plan=final.get("task_plan"),
                validation=final.get("validation"),
            )
        except Exception as exc:
            self.tracer.emit(
                trace_id=trace_id,
                session_id=session_id,
                event="agent",
                status="error",
                error=str(exc),
            )
            return QueryResponse(
                trace_id=trace_id,
                session_id=session_id,
                status="error",
                answer=f"任务失败：{exc}",
                errors=[str(exc)],
                fallback_used=True,
                evidence_summary={},
                execution_context={"fallback_used": True, "recursion_limit": 12},
            )

    async def arun(
        self, question: str, *, session_id: str | None = None, use_llm: bool = True
    ) -> QueryResponse:
        """Async entrypoint for FastAPI; sync tool nodes remain bounded by LangGraph."""
        session_id = session_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        initial: AgentState = {
            "question": question,
            "session_id": session_id,
            "trace_id": trace_id,
            "use_llm": use_llm,
            "tool_events": [],
            "errors": [],
            "step_count": 0,
        }
        try:
            final = await self.graph.ainvoke(
                initial,
                config={"configurable": {"thread_id": session_id}, "recursion_limit": 12},
            )
            status = self._response_status(final)
            return QueryResponse(
                trace_id=trace_id,
                session_id=session_id,
                status=status,
                answer=final.get("final_answer", ""),
                intent=final.get("intent"),
                charts=final.get("chart_paths", []),
                citations=final.get("citations", []),
                tool_events=final.get("tool_events", []),
                errors=final.get("errors", []),
                fallback_used=final.get("fallback_used", False),
                evidence_summary=self._evidence_summary(final),
                execution_context=self._execution_context(final),
                task_plan=final.get("task_plan"),
                validation=final.get("validation"),
            )
        except Exception as exc:
            self.tracer.emit(
                trace_id=trace_id,
                session_id=session_id,
                event="agent",
                status="error",
                error=str(exc),
            )
            return QueryResponse(
                trace_id=trace_id,
                session_id=session_id,
                status="error",
                answer=f"任务失败：{exc}",
                errors=[str(exc)],
                fallback_used=True,
                evidence_summary={},
                execution_context={"fallback_used": True, "recursion_limit": 12},
            )
