from dataclasses import replace

from finance_insight.agent import FinanceInsightAgent
from finance_insight.config import Settings, settings
from finance_insight.intent_parser import parse_intent
from finance_insight.tools import FinancialQueryTool


class FailingLLM:
    def chat(self, messages, *, response_format=None):
        raise RuntimeError("injected LLM outage")


def test_llm_outage_falls_back_to_deterministic_report(tmp_path):
    config = replace(
        settings,
        llm_api_key="test-key",
        artifact_dir=tmp_path / "artifacts",
        log_dir=tmp_path / "logs",
    )
    agent = FinanceInsightAgent(config)
    agent.llm = FailingLLM()
    result = agent.run("查询凯莱英2024年营业收入", use_llm=True)
    assert result.status == "partial"
    assert result.fallback_used
    expected = (
        FinancialQueryTool(config)
        .run(parse_intent("查询凯莱英2024年营业收入", config))
        .data["records"][0]["metric_value"]
    )
    assert f"{expected:,.2f}" in result.answer
    assert any("LLM 调用失败" in error for error in result.errors)


def test_database_failure_is_explainable(tmp_path):
    config = Settings(finance_db=tmp_path / "missing.sqlite3")
    tool = FinancialQueryTool(config)

    # SQL Tool returns a structured error instead of leaking an exception.
    class Dummy:
        companies = []
        metrics = []
        period = type("Period", (), {"years": []})()
        task_type = "query"

    result = tool.run(Dummy())
    assert result.status == "error" and "不存在" in result.error
