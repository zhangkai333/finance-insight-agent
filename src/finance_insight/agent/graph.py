from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from finance_insight.agent.state import AgentState
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
        graph.add_node("query_sql", self._query)
        graph.add_node("calculate", self._calculate)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("chart", self._chart)
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge(START, "parse")
        graph.add_edge("parse", "query_sql")
        graph.add_conditional_edges(
            "query_sql", self._after_query,
            {"calculate": "calculate", "retrieve": "retrieve", "chart": "chart", "synthesize": "synthesize"},
        )
        graph.add_conditional_edges(
            "calculate", self._after_calculate,
            {"retrieve": "retrieve", "chart": "chart", "synthesize": "synthesize"},
        )
        graph.add_conditional_edges(
            "retrieve", self._after_retrieve, {"chart": "chart", "synthesize": "synthesize"}
        )
        graph.add_edge("chart", "synthesize")
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
                    "backend", "requested_backend", "record_count", "scope",
                    "retrieval_mode", "embedding_provider", "fallback_reason",
                    "anomaly_count", "count",
                )
                if key in result.data
            },
        }
        self.tracer.emit(
            trace_id=state["trace_id"], session_id=state["session_id"],
            event=result.tool_name, status=result.status,
            latency_ms=event["latency_ms"], error=result.error,
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
                        trace_id=state["trace_id"], session_id=state["session_id"],
                        event="structured_output_fallback", status="partial", error=str(exc),
                    )
            else:
                intent = parse_intent(state["question"], self.config)
        except ValueError:
            previous = state.get("intent")
            if not previous:
                raise
            contextual_question = f"{previous.companies[0].stock_code} {state['question']}"
            intent = parse_intent(contextual_question, self.config)
            intent.question = state["question"]
            intent.parser = "deterministic-rule-v1+session-context"
            parse_fallback = True
        self.tracer.emit(
            trace_id=state["trace_id"], session_id=state["session_id"],
            event="parse_intent", status="success",
            intent=intent.model_dump(), prompt_version=PROMPT_VERSION,
        )
        return {
            "intent": intent, "tool_events": [], "errors": [],
            "chart_paths": [], "citations": [],
            "fallback_used": parse_fallback, "step_count": 1,
        }

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
        result = self._call_tool(
            lambda: self.rag.run(
                state["intent"],
                query="主要原因" if state.get("anomalies") else "经营情况",
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

    def _after_query(self, state: AgentState) -> str:
        if not state.get("financial_data"):
            return "synthesize"
        if state["intent"].needs_calculation or state["intent"].needs_anomaly_detection or state["intent"].needs_chart:
            return "calculate"
        if state["intent"].needs_rag:
            return "retrieve"
        return "synthesize"

    def _after_calculate(self, state: AgentState) -> str:
        if state["intent"].needs_rag or bool(state.get("anomalies")):
            return "retrieve"
        if state["intent"].needs_chart:
            return "chart"
        return "synthesize"

    def _after_retrieve(self, state: AgentState) -> str:
        return "chart" if state["intent"].needs_chart else "synthesize"

    def _deterministic_answer(self, state: AgentState) -> str:
        if not state.get("financial_data"):
            return "查询失败：" + "；".join(state.get("errors", []) or ["没有匹配数据"])
        title = "跨公司财务排名" if state["intent"].task_type == "ranking" else f"{state['intent'].companies[0].company_name} 财务分析"
        lines = [f"## {title}", "", "### 结构化财务事实"]
        if state["intent"].task_type == "ranking":
            for row in state["financial_data"][:10]:
                lines.append(f"- 第{row['rank']}名 {row['company_name']}：{float(row['metric_value']):,.2f}{row['normalized_unit']}")
        elif state.get("calculations", {}).get("series"):
            for item in state["calculations"]["series"]:
                values = "；".join(
                    f"{p['year']}年 {p['value']:,.2f}{p['unit']}"
                    + (f"（同比 {p['yoy_pct']:+.2f}%）" if p.get("yoy_pct") is not None else "")
                    for p in item["points"]
                )
                cagr = f"，期间 CAGR {item['cagr_pct']:+.2f}%" if item.get("cagr_pct") is not None else ""
                lines.append(f"- {item['metric_name']}：{values}{cagr}")
        else:
            for row in state["financial_data"][:20]:
                lines.append(f"- {row['report_year']}年 {row['metric_name']}：{float(row['metric_value']):,.2f}{row['normalized_unit']}")
        if state.get("anomalies"):
            lines.extend(["", "### 异常检测"])
            lines.extend(f"- {item['year']}年：{item['message']}" for item in state["anomalies"])
        if state.get("rag_chunks"):
            lines.extend(["", "### 年报依据"])
            for chunk in state["rag_chunks"][:3]:
                snippet = " ".join(chunk["content"].split())[:220]
                lines.append(f"- {snippet}……（{chunk['source_file']}，第{chunk['page_number']}页）")
        if state.get("chart_paths"):
            lines.extend(["", "### 图表", *[f"- {path}" for path in state["chart_paths"]]])
        lines.extend([
            "",
            "> 说明：数值来自结构化财务事实库，变化率由 Python 计算，原因引用来自年报；本结果用于经营分析，不构成投资建议。",
        ])
        return "\n".join(lines)

    def _synthesize(self, state: AgentState) -> dict[str, Any]:
        answer = self._deterministic_answer(state)
        fallback = state.get("fallback_used", False)
        if state.get("use_llm", True) and self.config.llm_enabled:
            evidence = {
                "question": state["question"],
                "financial_data": state.get("financial_data", []),
                "calculations": state.get("calculations", {}),
                "rag_chunks": state.get("rag_chunks", [])[:4],
            }
            try:
                answer = self.llm.chat([
                    {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(evidence, ensure_ascii=False, default=str)},
                ]).content
                fallback = False
            except Exception as exc:
                self.tracer.emit(
                    trace_id=state["trace_id"], session_id=state["session_id"],
                    event="llm_fallback", status="partial", error=str(exc),
                )
                return {
                    "final_answer": answer, "fallback_used": True,
                    "errors": state.get("errors", []) + [f"LLM 调用失败，已降级为确定性报告: {exc}"],
                    "step_count": state.get("step_count", 0) + 1,
                }
        self.tracer.emit(
            trace_id=state["trace_id"], session_id=state["session_id"],
            event="synthesize", status="success", fallback_used=fallback,
        )
        return {"final_answer": answer, "fallback_used": fallback, "step_count": state.get("step_count", 0) + 1}

    def run(self, question: str, *, session_id: str | None = None, use_llm: bool = True) -> QueryResponse:
        session_id = session_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        initial: AgentState = {
            "question": question, "session_id": session_id, "trace_id": trace_id,
            "use_llm": use_llm, "tool_events": [], "errors": [], "step_count": 0,
        }
        try:
            final = self.graph.invoke(
                initial,
                config={"configurable": {"thread_id": session_id}, "recursion_limit": 12},
            )
            status = "success" if not final.get("errors") else ("partial" if final.get("financial_data") else "error")
            return QueryResponse(
                trace_id=trace_id, session_id=session_id, status=status,
                answer=final.get("final_answer", ""), intent=final.get("intent"),
                charts=final.get("chart_paths", []), citations=final.get("citations", []),
                tool_events=final.get("tool_events", []), errors=final.get("errors", []),
                fallback_used=final.get("fallback_used", False),
            )
        except Exception as exc:
            self.tracer.emit(
                trace_id=trace_id, session_id=session_id,
                event="agent", status="error", error=str(exc),
            )
            return QueryResponse(
                trace_id=trace_id, session_id=session_id, status="error",
                answer=f"任务失败：{exc}", errors=[str(exc)], fallback_used=True,
            )

