from __future__ import annotations

import shutil
from dataclasses import replace

import pytest

from finance_insight.agent import FinanceInsightAgent
from finance_insight.agent.planner import build_task_plan
from finance_insight.agent.validator import validate_evidence
from finance_insight.config import settings
from finance_insight.intent_parser import parse_intent
from finance_insight.rag.query_rewrite import rewrite_financial_query
from finance_insight.tools.rag_tool import (
    METRIC_EVIDENCE_TERMS,
    _metric_excerpt,
    has_cause_evidence,
    has_metric_evidence,
)


@pytest.fixture
def finance_agent(tmp_path):
    finance_db = tmp_path / "finance.sqlite3"
    rag_db = tmp_path / "rag.sqlite3"
    shutil.copy2(settings.finance_db, finance_db)
    shutil.copy2(settings.rag_db, rag_db)
    config = replace(
        settings,
        finance_db=finance_db,
        rag_db=rag_db,
        artifact_dir=tmp_path / "artifacts",
        log_dir=tmp_path / "logs",
        llm_api_key=None,
        rag_backend="sqlite",
        rag_max_retrieval_rounds=2,
    )
    return FinanceInsightAgent(config)


def test_rewritten_fts_expression_does_not_include_query_syntax():
    rewritten = rewrite_financial_query('凯莱英 OR "x" -删除 营业收入下降原因')

    assert rewritten.fts_expression
    assert "删除" not in rewritten.fts_expression
    assert all(
        part.startswith('"') and part.endswith('"')
        for part in rewritten.fts_expression.split(" OR ")
    )


def test_planner_dependencies_are_ordered():
    intent = parse_intent("分析凯莱英2022到2024年营业收入异常变化并解释原因")
    plan = build_task_plan(intent.question, intent)
    positions = {task.id: index for index, task in enumerate(plan.subtasks)}

    assert plan.strategy == "fusion"
    assert all(
        positions[dependency] < positions[task.id]
        for task in plan.subtasks
        for dependency in task.dependencies
    )


def test_attribution_returns_citations_and_retrieval_metadata(finance_agent):
    result = finance_agent.run(
        "分析凯莱英2022到2024年营业收入异常变化并解释原因",
        use_llm=False,
    )
    rag_event = next(
        event for event in result.tool_events if event["tool_name"] == "annual_report_search"
    )

    assert result.status == "success"
    assert result.citations
    assert all(
        any(term in citation["snippet"] for term in ("营业收入", "营业总收入", "营收"))
        for citation in result.citations
    )
    assert all("净利润" not in citation["snippet"] for citation in result.citations)
    assert result.task_plan is not None and result.task_plan.strategy == "fusion"
    assert result.validation is not None and result.validation.status == "passed"
    assert rag_event["details"]["reranker"] == "lexical-metadata-v1"
    assert 1 <= rag_event["details"]["retrieval_attempts"] <= 2
    assert "evidence_score" in rag_event["details"]
    assert rag_event["fallback_used"] is False
    assert rag_event["details"]["effective_rag_backend"] == "sqlite"


def test_validator_warns_when_attribution_has_no_citations():
    intent = parse_intent("分析凯莱英2022到2024年营业收入异常变化并解释原因")
    report = validate_evidence(intent, [], {}, [])

    assert report.status == "warning"
    assert any("没有返回原文引用" in warning for warning in report.warnings)


def test_validator_warns_when_metric_citation_has_no_cause_evidence():
    intent = parse_intent("分析凯莱英2022到2024年营业收入变化并解释原因")
    report = validate_evidence(
        intent,
        [],
        {},
        [{"matched_metric": "revenue", "snippet": "营业收入本期为100亿元。"}],
    )

    assert report.status == "warning"
    cause = next(check for check in report.checks if check["name"] == "cause_evidence")
    assert not cause["passed"]


def test_revenue_cause_excerpt_can_also_mention_net_profit():
    excerpt = _metric_excerpt(
        "報告期，营业收入下降主要系产品销量减少所致，净利润也因此下降。",
        ("营业收入", "营业总收入", "营收"),
    )

    assert "营业收入" in excerpt
    assert "主要系" in excerpt
    assert "净利润" in excerpt


def test_multi_metric_attribution_covers_each_metric(finance_agent):
    result = finance_agent.run(
        "分析凯莱英2022到2024年营业收入和归母净利润变化并结合年报解释原因",
        use_llm=False,
    )

    assert result.status == "success"
    assert result.intent is not None
    assert set(result.intent.metrics) == {"revenue", "net_profit_attributable"}
    assert result.validation is not None and result.validation.status == "passed"
    coverage = next(
        check for check in result.validation.checks if check["name"] == "citation_coverage"
    )
    assert set(coverage["covered_metrics"]) == set(result.intent.metrics)
    revenue = next(c for c in result.citations if c["matched_metric"] == "revenue")
    net_profit = next(
        c for c in result.citations if c["matched_metric"] == "net_profit_attributable"
    )
    assert any(term in revenue["snippet"] for term in ("营业收入", "营业总收入", "营收"))
    assert any(
        term in net_profit["snippet"]
        for term in ("归母净利润", "归属于上市公司股东的净利润", "净利润")
    )
    assert revenue["page_number"] > 0 and net_profit["page_number"] > 0
    assert f"第{revenue['page_number']}页" in result.answer
    assert f"第{net_profit['page_number']}页" in result.answer


def test_broken_pdf_metric_keeps_numbered_annual_causes():
    terms = METRIC_EVIDENCE_TERMS["net_profit_attributable"]
    excerpt = _metric_excerpt(
        "本报告期归属于上市公司股东的净 利润9.49亿元，同比下降58.17%，主要原因如下："
        "（1）去年大订单盈利较高，今年无相关收入；（2）新兴业务处于爬坡期。"
        "其他事项与该指标无关。",
        terms,
    )
    assert has_metric_evidence(excerpt, terms)
    assert has_cause_evidence(excerpt, terms)
    assert "新兴业务处于爬坡期" in excerpt
    assert "其他事项" not in excerpt


@pytest.mark.parametrize(
    "text,expected",
    [
        ("基于地理位置划分的营业收入，详见附注五、41。", False),
        ("营业收入中包括大订单，详见附注。", False),
        ("由于设备安装调试，暂无法估计预计的年营业收入、利润。", False),
        ("基于市场需求增长放缓、行业竞争加剧等因素，公司营业收入承压。", True),
        ("营业收入变动原因说明：收入降幅32.64%，主要系销量减少所致。", True),
    ],
)
def test_cause_evidence_requires_metric_and_change(text, expected):
    assert has_cause_evidence(text, METRIC_EVIDENCE_TERMS["revenue"]) is expected


def test_shared_passage_covers_each_explicit_metric():
    intent = parse_intent("分析凯莱英2024年营业收入和归母净利润下降原因")
    snippet = "营业收入和归母净利润下降，主要系产品销量减少所致。"
    report = validate_evidence(
        intent,
        [],
        {},
        [{"matched_metric": metric, "snippet": snippet} for metric in intent.metrics],
    )
    cause = next(check for check in report.checks if check["name"] == "cause_evidence")
    assert cause["passed"]


def test_revenue_cause_does_not_cover_unrelated_profit_sentence():
    assert not has_cause_evidence(
        "营业收入下降主要系订单减少所致。归母净利润本期100亿元。",
        METRIC_EVIDENCE_TERMS["net_profit_attributable"],
    )


def test_validator_warns_when_one_metric_citation_is_missing():
    intent = parse_intent("分析凯莱英2022到2024年营业收入和归母净利润变化并结合年报解释原因")
    citations = [{"matched_metric": "revenue", "snippet": "营业总收入下降主要系大订单减少"}]
    report = validate_evidence(intent, [], {}, citations)

    coverage = next(check for check in report.checks if check["name"] == "citation_coverage")
    assert not coverage["passed"]
    assert coverage["missing_metrics"] == ["net_profit_attributable"]
    assert any("部分指标缺少相关原文引用" in warning for warning in report.warnings)


@pytest.mark.anyio
async def test_async_entrypoint_returns_plan_and_validation(finance_agent):
    result = await finance_agent.arun("查询凯莱英2024年营业收入", use_llm=False)

    assert result.status == "success"
    assert result.task_plan is not None
    assert result.validation is not None
    assert [event["tool_name"] for event in result.tool_events] == ["financial_query"]


def test_ambiguous_question_requests_clarification_without_tools(finance_agent):
    result = finance_agent.run("请查询某个公司的情况", use_llm=False)

    assert result.status == "partial"
    assert result.task_plan is not None and result.task_plan.strategy == "clarification"
    assert result.task_plan.clarification_question
    assert result.validation is not None and result.validation.status == "warning"
    assert result.tool_events == []
    assert result.errors == []


def test_rag_partial_with_financial_facts_returns_partial(finance_agent, monkeypatch):
    original = finance_agent.rag.run

    def partial_result(*args, **kwargs):
        result = original(*args, **kwargs)
        result.status = "partial"
        return result

    monkeypatch.setattr(finance_agent.rag, "run", partial_result)
    result = finance_agent.run(
        "查询凯莱英2024年营业收入并结合年报解释原因",
        use_llm=False,
    )

    assert result.status == "partial"


def test_warning_validation_never_returns_success(finance_agent):
    result = finance_agent.run("查询凯莱英2024年营业收入", use_llm=False)
    assert result.validation is not None

    state = {
        "task_plan": result.task_plan,
        "validation": result.validation.model_copy(update={"status": "warning"}),
        "financial_data": result.evidence_summary["facts"],
        "citations": [],
        "tool_events": [],
        "errors": [],
    }
    assert FinanceInsightAgent._response_status(state) == "partial"


def test_same_session_does_not_leak_previous_turn_evidence(finance_agent):
    session_id = "state-isolation-regression"
    attribution = finance_agent.run(
        "分析凯莱英2022到2024年营业收入异常变化并解释原因",
        session_id=session_id,
        use_llm=False,
    )
    simple_query = finance_agent.run(
        "查询凯莱英2024年营业收入",
        session_id=session_id,
        use_llm=False,
    )

    assert attribution.citations
    assert simple_query.status == "success"
    assert simple_query.citations == []
    assert len(simple_query.evidence_summary["facts"]) == 1
    assert simple_query.evidence_summary["calculations"]["series"] == []
    assert [event["tool_name"] for event in simple_query.tool_events] == ["financial_query"]
