from pathlib import Path

from finance_insight.config import Settings
from finance_insight.tools.sql_tool import FinancialQueryTool


def test_mysql_connection_creation_error_is_preserved(tmp_path):
    config = Settings(
        finance_db=tmp_path / "finance.sqlite3",
        finance_backend="mysql",
        mysql_fallback_to_sqlite=False,
    )
    tool = FinancialQueryTool(config)

    def fail():
        raise ConnectionError("injected mysql connection failure")

    tool._mysql_connection = fail
    class Dummy:
        companies = []
        metrics = []
        period = type("Period", (), {"years": []})()
        task_type = "query"

    result = tool.run(Dummy())
    assert result.status == "error"
    assert "injected mysql connection failure" in result.error
    assert "generator didn't yield" not in result.error


def test_mysql_and_sqlite_failures_are_both_observable(tmp_path):
    config = Settings(
        finance_db=tmp_path / "missing.sqlite3",
        finance_backend="mysql",
        mysql_fallback_to_sqlite=True,
    )
    tool = FinancialQueryTool(config)

    def fail():
        raise ConnectionError("injected mysql outage")

    tool._mysql_connection = fail
    class Dummy:
        companies = []
        metrics = []
        period = type("Period", (), {"years": []})()
        task_type = "query"

    result = tool.run(Dummy())
    assert result.status == "error"
    assert result.fallback_used
    assert "injected mysql outage" in result.error
    assert "财务数据库不存在" in result.error
