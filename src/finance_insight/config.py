from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_local_dotenv(path: Path = ROOT_DIR / ".env") -> None:
    """Load local environment values without overriding the process environment."""
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(name, value)


_load_local_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _bool_env(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    finance_db: Path = Path(_env("FINANCE_DB", str(ROOT_DIR / "data" / "finance_insight.sqlite3")))
    rag_db: Path = Path(_env("RAG_DB", str(ROOT_DIR / "data" / "rag.sqlite3")))
    artifact_dir: Path = Path(_env("ARTIFACT_DIR", str(ROOT_DIR / "data" / "artifacts")))
    log_dir: Path = Path(_env("LOG_DIR", str(ROOT_DIR / "data" / "logs")))
    eval_dataset: Path = Path(_env("EVAL_DATASET", str(ROOT_DIR / "evals" / "dataset.json")))
    eval_output: Path = Path(_env("EVAL_OUTPUT", str(ROOT_DIR / "data" / "evaluation" / "report.json")))
    finance_backend: str = (_env("FINANCE_BACKEND", "sqlite") or "sqlite").lower()
    mysql_host: str = _env("MYSQL_HOST", "127.0.0.1") or "127.0.0.1"
    mysql_port: int = int(_env("MYSQL_PORT", "3306") or 3306)
    mysql_database: str = _env("MYSQL_DATABASE", "finance_insight") or "finance_insight"
    mysql_user: str = _env("MYSQL_USER", "finance") or "finance"
    mysql_password: str = _env("MYSQL_PASSWORD", "change-me") or "change-me"
    mysql_connect_timeout_seconds: int = int(_env("MYSQL_CONNECT_TIMEOUT_SECONDS", "5") or 5)
    mysql_read_timeout_seconds: int = int(_env("MYSQL_READ_TIMEOUT_SECONDS", "10") or 10)
    mysql_pool_size: int = int(_env("MYSQL_POOL_SIZE", "4") or 4)
    mysql_pool_acquire_timeout_seconds: float = float(_env("MYSQL_POOL_ACQUIRE_TIMEOUT_SECONDS", "5") or 5)
    mysql_fallback_to_sqlite: bool = _bool_env("MYSQL_FALLBACK_TO_SQLITE", True)
    llm_api_key: str | None = _env("DEEPSEEK_API_KEY") or _env("LLM_API_KEY")
    llm_base_url: str = _env("LLM_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com"
    llm_model: str = _env("LLM_MODEL", "deepseek-chat") or "deepseek-chat"
    llm_timeout_seconds: float = float(_env("LLM_TIMEOUT_SECONDS", "30") or 30)
    max_concurrent_requests: int = int(_env("MAX_CONCURRENT_REQUESTS", "2") or 2)
    request_queue_timeout_seconds: float = float(_env("REQUEST_QUEUE_TIMEOUT_SECONDS", "15") or 15)
    redis_url: str | None = _env("REDIS_URL")

    def __post_init__(self) -> None:
        if self.finance_backend not in {"sqlite", "mysql"}:
            raise ValueError("FINANCE_BACKEND 只能是 sqlite 或 mysql")
        if self.max_concurrent_requests < 1:
            raise ValueError("MAX_CONCURRENT_REQUESTS 必须大于 0")
        if self.request_queue_timeout_seconds <= 0:
            raise ValueError("REQUEST_QUEUE_TIMEOUT_SECONDS 必须大于 0")
        if self.mysql_read_timeout_seconds <= 0:
            raise ValueError("MYSQL_READ_TIMEOUT_SECONDS 必须大于 0")
        if self.mysql_pool_size < 1:
            raise ValueError("MYSQL_POOL_SIZE 必须大于 0")
        if self.mysql_pool_acquire_timeout_seconds <= 0:
            raise ValueError("MYSQL_POOL_ACQUIRE_TIMEOUT_SECONDS 必须大于 0")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
