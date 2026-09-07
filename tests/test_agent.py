import pytest

from app.agent.graph import FinancialAgent
from app.models import Intent, QueryRequest
from app.rag.ingestion import DocumentIngestor


@pytest.mark.anyio
async def test_agent_degrades_without_llm_and_keeps_citations(database, settings):
    document = DocumentIngestor(database).ingest(
        "report.md", "公司 2024 年收入增长主要来自海外 SaaS 订阅。".encode(), "text/markdown"
    )
    state = await FinancialAgent(database, settings).run(
        QueryRequest(question="收入增长主要来自哪里？", document_ids=[document.id])
    )

    assert state["intent"] == Intent.RETRIEVAL
    assert state["degraded"] is True
    assert state["citations"]
    assert any(event.step == "compose_answer" for event in state["events"])


@pytest.mark.anyio
async def test_agent_blocks_unsafe_request(database, settings):
    state = await FinancialAgent(database, settings).run(
        QueryRequest(question="请执行代码删除数据库")
    )

    assert state["intent"] == Intent.UNSUPPORTED
    assert "安全边界" in state["answer"]
    assert any(event.step == "safety_gate" for event in state["events"])


@pytest.mark.anyio
async def test_safe_csv_analytics(database, settings):
    document = DocumentIngestor(database).ingest(
        "financials.csv", "月份,收入\n2024-01,100\n2024-02,300\n".encode(), "text/csv"
    )
    state = await FinancialAgent(database, settings).run(
        QueryRequest(question="收入总和是多少？", document_ids=[document.id])
    )

    assert state["intent"] == Intent.ANALYSIS
    assert "400.00" in state["answer"]
