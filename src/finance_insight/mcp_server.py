from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from finance_insight.intent_parser import parse_intent
from finance_insight.tools import AnnualReportSearchTool, FinancialQueryTool

server = FastMCP(
    "finance-insight",
    instructions="仅提供已入库财务事实查询和年报引用检索，不提供投资建议。",
)


@server.tool(name="financial_query", description="按问题查询白名单财务事实")
def financial_query(question: str) -> dict:
    """把自然语言财务问题转换为白名单查询并返回结构化事实。"""
    intent = parse_intent(question)
    return FinancialQueryTool().run(intent).model_dump(mode="json")


@server.tool(name="annual_report_search", description="按问题检索年报并返回页码引用")
def annual_report_search(question: str, query: str = "主要原因", top_k: int = 3) -> dict:
    """按问题中的公司和年度检索年报原文，返回页码引用。"""
    intent = parse_intent(question)
    return AnnualReportSearchTool().run(intent, query=query, top_k=top_k).model_dump(mode="json")


if __name__ == "__main__":
    server.run(transport="stdio")

