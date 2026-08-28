import pytest

from finance_insight.intent_parser import parse_intent
from finance_insight.schemas import QueryIntent
from finance_insight.structured_output import validate_structured


def test_parse_comprehensive_intent():
    intent = parse_intent("分析凯莱英2022—2024年营业收入、净利润和ROE的变化，如果发现异常年份，结合年报分析原因，并生成趋势图")
    assert intent.companies[0].stock_code == "002821"
    assert intent.period.years == [2022, 2023, 2024]
    assert set(intent.metrics) == {"revenue", "net_profit_attributable", "roe"}
    assert intent.needs_rag and intent.needs_chart and intent.needs_anomaly_detection


def test_cross_company_ranking_without_named_company():
    intent = parse_intent("查询2024年营业收入排名")
    assert intent.task_type == "ranking" and len(intent.companies) == 10


def test_structured_output_repairs_code_fence_and_trailing_comma():
    raw = "```json\n{\"question\":\"查询凯莱英2024年营业收入\",\"companies\":[{\"stock_code\":\"002821\",\"company_name\":\"凯莱英\"}],\"period\":{\"years\":[2024]},\"metrics\":[\"revenue\"],\"needs_sql\":true,\"needs_calculation\":false,\"needs_rag\":false,\"needs_chart\":false,\"needs_anomaly_detection\":false,\"task_type\":\"query\",\"confidence\":0.9,}\n```"
    result = validate_structured(raw, QueryIntent)
    assert result.metrics == ["revenue"]


def test_unknown_company_is_explainable():
    with pytest.raises(ValueError, match="未识别"):
        parse_intent("查询不存在公司2024年营业收入")


def test_parse_intent_prefers_specific_overlapping_metric_aliases():
    assert parse_intent("查询凯莱英2024年扣非净利润").metrics == ["net_profit_excl_non_recurring"]
    assert parse_intent("查询凯莱英2024年经营现金流率").metrics == ["operating_cash_margin"]
    assert parse_intent("查询凯莱英2024年净资产收益率").metrics == ["roe"]
