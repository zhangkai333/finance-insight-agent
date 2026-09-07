import pytest

from app.config import Settings
from app.storage import Database


@pytest.fixture
def database(tmp_path):
    return Database(tmp_path / "test.db")


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "test.db", llm_api_key="", max_agent_retries=1)
