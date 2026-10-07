from finance_insight.agent import FinanceInsightAgent


def test_project_demo_question_has_fact_calculation_citation_and_chart():
    result = FinanceInsightAgent().run(
        "分析凯莱英2022—2024年营业收入、净利润和ROE的变化，如果发现异常年份，结合对应年报分析原因，并生成趋势图和分析报告。",
        use_llm=False,
    )
    assert "2024年" in result.answer
    assert "同比" in result.answer
    assert "第" in result.answer and "页" in result.answer
    assert result.charts
