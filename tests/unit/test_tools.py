from pathlib import Path

from finance_insight.intent_parser import parse_intent
from finance_insight.tools import AnnualReportSearchTool, ChartGenerationTool, FinancialAnalysisTool, FinancialQueryTool


def test_sql_tool_returns_three_years():
    intent = parse_intent("查询凯莱英2022到2024年营业收入")
    result = FinancialQueryTool().run(intent)
    assert result.status == "success" and result.data["record_count"] == 3
    assert [row["report_year"] for row in result.data["records"]] == [2022, 2023, 2024]


def test_analysis_computes_yoy_and_anomaly():
    intent = parse_intent("分析凯莱英2022到2024年营业收入异常变化")
    records = FinancialQueryTool().run(intent).data["records"]
    result = FinancialAnalysisTool().run(records, detect_anomalies=True)
    points = result.data["series"][0]["points"]
    assert points[1]["yoy_pct"] == -23.7
    assert result.data["anomaly_count"] >= 2


def test_rag_returns_citation_metadata():
    intent = parse_intent("结合年报解释凯莱英2024年净利润下降原因")
    result = AnnualReportSearchTool().run(intent, query="主要原因", top_k=2)
    assert result.status == "success" and len(result.citations) == 2
    assert all(item["page_number"] > 0 and item["source_file"] for item in result.citations)


def test_chart_generates_png(tmp_path):
    intent = parse_intent("绘制凯莱英2022到2024年营业收入趋势图")
    records = FinancialQueryTool().run(intent).data["records"]
    series = FinancialAnalysisTool().run(records).data["series"]
    tool = ChartGenerationTool()
    tool.output_dir = tmp_path
    result = tool.run(series, trace_id="unit")
    assert result.status == "success" and len(result.data["chart_paths"]) == 1
    assert Path(result.data["chart_paths"][0]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
