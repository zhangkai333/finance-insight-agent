from __future__ import annotations

import atexit
import importlib.util
import os
import shutil
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = PROJECT_ROOT / ".pytest-tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
DEMO_DATA_DIR = Path(tempfile.mkdtemp(prefix="finance-insight-demo-", dir=TEST_TMP_ROOT))


def _initialize_test_demo() -> None:
    script_path = PROJECT_ROOT / "scripts" / "init_demo_data.py"
    spec = importlib.util.spec_from_file_location("conftest_init_demo_data", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.initialize_demo_data(DEMO_DATA_DIR)

    os.environ.update(
        {
            "DEMO_MODE": "true",
            "FINANCE_BACKEND": "sqlite",
            "RAG_BACKEND": "sqlite",
            "FINANCE_DB": str(DEMO_DATA_DIR / "finance_insight.sqlite3"),
            "RAG_DB": str(DEMO_DATA_DIR / "rag.sqlite3"),
            "ARTIFACT_DIR": str(DEMO_DATA_DIR / "artifacts"),
            "LOG_DIR": str(DEMO_DATA_DIR / "logs"),
            "UPLOAD_DATABASE_PATH": str(DEMO_DATA_DIR / "legacy" / "finagent_runtime.db"),
            "EVAL_DATASET": str(PROJECT_ROOT / "evals" / "dataset_demo.json"),
            "EVAL_OUTPUT": str(DEMO_DATA_DIR / "evaluation" / "report.json"),
            "LLM_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            "EMBEDDING_API_KEY": "",
            "REDIS_URL": "",
            "PYTHONUTF8": "1",
        }
    )


_initialize_test_demo()
atexit.register(shutil.rmtree, DEMO_DATA_DIR, ignore_errors=True)

from finance_insight.legacy.config import Settings  # noqa: E402
from finance_insight.legacy.storage import Database  # noqa: E402


@pytest.fixture
def database(tmp_path):
    return Database(tmp_path / "test.db")


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "test.db", llm_api_key="", max_agent_retries=1)
