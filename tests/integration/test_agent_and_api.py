import time
from pathlib import Path

from fastapi.testclient import TestClient

from finance_insight.agent import FinanceInsightAgent
from finance_insight.api import app


def test_langgraph_agent_e2e():
    result = FinanceInsightAgent().run(
        "分析凯莱英2022—2024年营业收入、净利润和ROE的变化，如果发现异常年份，结合对应年报分析原因，并生成趋势图和分析报告。",
        use_llm=False,
    )
    assert result.status == "success"
    assert [event["tool_name"] for event in result.tool_events] == [
        "financial_query", "financial_analysis", "annual_report_search", "chart_generation"
    ]
    assert len(result.charts) == 3 and all(Path(path).exists() for path in result.charts)
    assert result.citations and "年报依据" in result.answer


def test_session_context_resolves_follow_up():
    agent = FinanceInsightAgent()
    session = "memory-test"
    first = agent.run("查询凯莱英2022到2024年营业收入趋势", session_id=session, use_llm=False)
    second = agent.run("再看净利润趋势", session_id=session, use_llm=False)
    assert first.status == "success" and second.status == "success"
    assert second.intent.companies[0].stock_code == "002821"
    assert second.intent.parser.endswith("session-context")


def test_api_sync_async_and_session():
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    response = client.post("/v1/query", json={"question": "查询凯莱英2022到2024年营业收入趋势", "use_llm": False})
    assert response.status_code == 200 and response.json()["status"] == "success"
    session_id = response.json()["session_id"]
    assert client.get(f"/v1/sessions/{session_id}").status_code == 200
    task = client.post("/v1/tasks", json={"question": "查询2024年营业收入排名", "use_llm": False}).json()
    state = {}
    for _ in range(30):
        state = client.get(f"/v1/tasks/{task['task_id']}").json()
        if state["status"] in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert state["status"] == "completed" and state["result"]["status"] == "success"



def test_workspace_static_health_and_browser_artifacts():
    client = TestClient(app)

    workspace = client.get("/")
    assert workspace.status_code == 200
    assert "FinanceInsight · 财报分析工作台" in workspace.text
    assert "输入问题后，这里将展示完整分析结果" in workspace.text

    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]

    health = client.get("/health").json()
    assert health["finance_backend_requested"] in {"sqlite", "mysql"}
    assert health["finance_backend_effective"] in {"sqlite", "mysql"}
    assert isinstance(health["finance_backend_ready"], bool)

    response = client.post(
        "/v1/query",
        json={"question": "绘制凯莱英2022到2024年营业收入趋势图", "use_llm": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["charts"] and all(path.startswith("/artifacts/") for path in payload["charts"])
    assert "/app/data/" not in payload["answer"]
    assert all(path in payload["answer"] for path in payload["charts"])
    for chart_url in payload["charts"]:
        chart = client.get(chart_url)
        assert chart.status_code == 200
        assert chart.headers["content-type"] == "image/png"


def test_evaluation_api_completes_fixed_regression_suite():
    client = TestClient(app)
    created = client.post("/v1/evaluations", json={"use_llm": False})
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    state = {}
    for _ in range(100):
        state = client.get(f"/v1/evaluations/{task_id}").json()
        if state["status"] in {"completed", "failed"}:
            break
        time.sleep(0.1)

    assert state["status"] == "completed"
    summary = state["result"]
    assert summary["cases"] == 6
    assert summary["task_success_rate"] == 1.0
    assert all(item["task_success"] for item in summary["results"])
    latest = client.get("/v1/evaluation/latest").json()
    assert latest["cases"] == 6 and latest["task_success_rate"] == 1.0
