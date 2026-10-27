from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from finance_insight.agent import FinanceInsightAgent
from finance_insight.config import Settings
from finance_insight.rag.hybrid import HybridRetriever

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "init_demo_data.py"
SPEC = importlib.util.spec_from_file_location("init_demo_data", SCRIPT_PATH)
assert SPEC and SPEC.loader
DEMO_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO_MODULE)


def test_demo_initializer_builds_complete_portable_runtime(tmp_path):
    data_dir = tmp_path / "data"
    summary = DEMO_MODULE.initialize_demo_data(data_dir)

    finance_db = data_dir / "finance_insight.sqlite3"
    rag_db = data_dir / "rag.sqlite3"
    assert summary["status"] == "PASS"
    assert summary["finance"]["facts"] == 300
    assert summary["rag"]["documents"] == 10
    assert summary["rag"]["chunks"] == 20
    assert summary["rag"]["vectors"] == 20

    with sqlite3.connect(finance_db) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM financial_facts WHERE quality_status='synthetic_demo_only'"
            ).fetchone()[0]
            == 300
        )
        assert (
            con.execute("SELECT COUNT(DISTINCT source_file) FROM financial_facts").fetchone()[0]
            == 1
        )

    with sqlite3.connect(rag_db) as con:
        content = con.execute(
            "SELECT content FROM document_chunks ORDER BY chunk_id LIMIT 1"
        ).fetchone()[0]
        assert "合成演示材料" in content and "不是真实年报" in content
    assert HybridRetriever(rag_db).available()

    config = Settings(
        finance_db=finance_db,
        rag_db=rag_db,
        artifact_dir=tmp_path / "artifacts",
        log_dir=tmp_path / "logs",
        llm_api_key=None,
        redis_url=None,
    )
    agent = FinanceInsightAgent(config)

    point = agent.run("查询凯莱英2024年营业收入", use_llm=False)
    trend = agent.run("分析凯莱英2022到2024年营业收入趋势", use_llm=False)
    rag = agent.run("结合年报解释凯莱英2024年营业收入变化原因", use_llm=False)
    chart = agent.run("绘制凯莱英2022到2024年营业收入趋势图", use_llm=False)

    assert point.status == "success" and "2024年" in point.answer
    assert trend.status == "success" and "同比" in trend.answer
    assert rag.status == "success" and rag.citations and "合成演示材料" in rag.answer
    assert chart.status == "success" and len(chart.charts) == 1
    assert Path(chart.charts[0]).is_file()


def test_demo_initializer_refuses_to_overwrite_existing_database(tmp_path):
    data_dir = tmp_path / "data"
    DEMO_MODULE.initialize_demo_data(data_dir)

    try:
        DEMO_MODULE.initialize_demo_data(data_dir)
    except FileExistsError as exc:
        assert "拒绝覆盖" in str(exc)
    else:
        raise AssertionError("initializer should refuse to overwrite existing databases")
