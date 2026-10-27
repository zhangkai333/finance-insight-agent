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
    finance_schema: Path = Path(_env("FINANCE_SCHEMA", str(ROOT_DIR / "db" / "schema.sql")))
    rag_schema: Path = Path(_env("RAG_SCHEMA", str(ROOT_DIR / "db" / "rag_schema.sql")))
    pdf_ingestion_dir: Path = Path(
        _env("PDF_INGESTION_DIR", str(ROOT_DIR / "data" / "processed" / "pdf_ingestion"))
    )
    pdf_llm_max_chars: int = int(_env("PDF_LLM_MAX_CHARS", "180000") or 180000)
    artifact_dir: Path = Path(_env("ARTIFACT_DIR", str(ROOT_DIR / "data" / "artifacts")))
    log_dir: Path = Path(_env("LOG_DIR", str(ROOT_DIR / "data" / "logs")))
    eval_dataset: Path = Path(_env("EVAL_DATASET", str(ROOT_DIR / "evals" / "dataset_demo.json")))
    eval_output: Path = Path(
        _env("EVAL_OUTPUT", str(ROOT_DIR / "data" / "evaluation" / "report.json"))
    )
    demo_mode: bool = _bool_env("DEMO_MODE", False)
    finance_backend: str = (_env("FINANCE_BACKEND", "sqlite") or "sqlite").lower()
    mysql_host: str = _env("MYSQL_HOST", "127.0.0.1") or "127.0.0.1"
    mysql_port: int = int(_env("MYSQL_PORT", "3306") or 3306)
    mysql_database: str = _env("MYSQL_DATABASE", "finance_insight") or "finance_insight"
    mysql_user: str = _env("MYSQL_USER", "finance") or "finance"
    mysql_password: str = _env("MYSQL_PASSWORD", "change-me") or "change-me"
    mysql_connect_timeout_seconds: int = int(_env("MYSQL_CONNECT_TIMEOUT_SECONDS", "5") or 5)
    mysql_read_timeout_seconds: int = int(_env("MYSQL_READ_TIMEOUT_SECONDS", "10") or 10)
    mysql_pool_size: int = int(_env("MYSQL_POOL_SIZE", "4") or 4)
    mysql_pool_acquire_timeout_seconds: float = float(
        _env("MYSQL_POOL_ACQUIRE_TIMEOUT_SECONDS", "5") or 5
    )
    mysql_fallback_to_sqlite: bool = _bool_env("MYSQL_FALLBACK_TO_SQLITE", True)
    llm_api_key: str | None = _env("DEEPSEEK_API_KEY") or _env("LLM_API_KEY")
    llm_base_url: str = (
        _env("LLM_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com"
    )
    llm_model: str = _env("LLM_MODEL", "deepseek-chat") or "deepseek-chat"
    llm_timeout_seconds: float = float(_env("LLM_TIMEOUT_SECONDS", "30") or 30)
    llm_temperature: float = float(_env("LLM_TEMPERATURE", "0.2") or 0.2)
    rag_backend: str = (_env("RAG_BACKEND", "sqlite") or "sqlite").lower()
    embedding_base_url: str = (
        _env("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
        or "https://api.siliconflow.cn/v1"
    )
    embedding_api_key: str | None = _env("EMBEDDING_API_KEY")
    embedding_model: str = _env("EMBEDDING_MODEL", "BAAI/bge-m3") or "BAAI/bge-m3"
    embedding_batch_size: int = int(_env("EMBEDDING_BATCH_SIZE", "20") or 20)
    embedding_concurrency: int = int(_env("EMBEDDING_CONCURRENCY", "8") or 8)
    chroma_path: Path = Path(_env("CHROMA_PATH", str(ROOT_DIR / "data" / ".cache" / "chroma_db")))
    chroma_collection: str = _env("CHROMA_COLLECTION", "report_knowledge") or "report_knowledge"
    bm25_k1: float = float(_env("BM25_K1", "1.5") or 1.5)
    bm25_b: float = float(_env("BM25_B", "0.75") or 0.75)
    rag_vector_weight: float = float(_env("RAG_VECTOR_WEIGHT", "0.6") or 0.6)
    rag_bm25_weight: float = float(_env("RAG_BM25_WEIGHT", "0.4") or 0.4)
    rag_max_retrieval_rounds: int = int(_env("RAG_MAX_RETRIEVAL_ROUNDS", "2") or 2)
    rerank_max_chars: int = int(_env("RERANK_MAX_CHARS", "200") or 200)
    rag_chunk_max_chars_for_llm: int = int(_env("RAG_CHUNK_MAX_CHARS_FOR_LLM", "500") or 500)
    max_concurrent_requests: int = int(_env("MAX_CONCURRENT_REQUESTS", "2") or 2)
    request_queue_timeout_seconds: float = float(_env("REQUEST_QUEUE_TIMEOUT_SECONDS", "15") or 15)
    redis_url: str | None = _env("REDIS_URL")
    upload_database: Path = Path(
        _env("UPLOAD_DATABASE_PATH", str(ROOT_DIR / "data" / "legacy" / "finagent_runtime.db"))
    )
    max_upload_mb: int = int(_env("MAX_UPLOAD_MB", "20") or 20)

    def __post_init__(self) -> None:
        if self.finance_backend not in {"sqlite", "mysql"}:
            raise ValueError("FINANCE_BACKEND 只能是 sqlite 或 mysql")
        if self.rag_backend not in {"sqlite", "chroma", "production"}:
            raise ValueError("RAG_BACKEND 只能是 sqlite、chroma 或 production")
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
        if self.max_upload_mb < 1:
            raise ValueError("MAX_UPLOAD_MB 必须大于 0")
        if self.pdf_llm_max_chars < 1000:
            raise ValueError("PDF_LLM_MAX_CHARS 必须至少为 1000")
        if not 0 <= self.llm_temperature <= 2:
            raise ValueError("LLM_TEMPERATURE 必须在 0 到 2 之间")
        if self.embedding_batch_size < 1 or self.embedding_concurrency < 1:
            raise ValueError("Embedding 批大小和并发数必须大于 0")
        if self.rag_max_retrieval_rounds not in {1, 2}:
            raise ValueError("RAG_MAX_RETRIEVAL_ROUNDS 必须为 1 或 2")
        if self.rag_vector_weight < 0 or self.rag_bm25_weight < 0:
            raise ValueError("RAG 融合权重不能为负数")
        if self.rag_vector_weight + self.rag_bm25_weight <= 0:
            raise ValueError("RAG 融合权重之和必须大于 0")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
