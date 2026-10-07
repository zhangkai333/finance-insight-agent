import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from finance_insight.legacy.models import Intent, TraceEvent, utc_now

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    row_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    content,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS financial_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    session_id TEXT,
    status TEXT NOT NULL,
    answer TEXT,
    intent TEXT,
    degraded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_ms REAL,
    input_summary TEXT NOT NULL DEFAULT '{}',
    output_summary TEXT NOT NULL DEFAULT '{}',
    error TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    root_cause TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bad_cases (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    question TEXT NOT NULL,
    expected_intent TEXT NOT NULL,
    actual_intent TEXT,
    answer TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._init_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as connection:
                connection.executescript(SCHEMA)
            self._initialized = True

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_trace(self, trace_id: str, question: str, session_id: str | None) -> None:
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO traces(id, question, session_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (trace_id, question, session_id, "running", utc_now().isoformat()),
            )

    def add_event(self, trace_id: str, event: TraceEvent) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO trace_events(
                    trace_id, step, status, started_at, duration_ms,
                    input_summary, output_summary, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    event.step,
                    event.status,
                    event.started_at.isoformat(),
                    event.duration_ms,
                    json.dumps(event.input_summary, ensure_ascii=False),
                    json.dumps(event.output_summary, ensure_ascii=False),
                    event.error,
                ),
            )

    def finish_trace(
        self,
        trace_id: str,
        *,
        status: str,
        answer: str | None = None,
        intent: Intent | None = None,
        degraded: bool = False,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE traces SET status=?, answer=?, intent=?, degraded=?, completed_at=?
                WHERE id=?""",
                (
                    status,
                    answer,
                    intent.value if intent else None,
                    int(degraded),
                    utc_now().isoformat(),
                    trace_id,
                ),
            )

    def get_trace(self, trace_id: str) -> sqlite3.Row | None:
        self.initialize()
        with self.connect() as connection:
            return connection.execute("SELECT * FROM traces WHERE id=?", (trace_id,)).fetchone()

    def get_trace_events(self, trace_id: str) -> list[sqlite3.Row]:
        self.initialize()
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM trace_events WHERE trace_id=? ORDER BY id", (trace_id,)
            ).fetchall()

    def create_feedback(
        self, feedback_id: str, trace_id: str, rating: int, comment: str | None, root_cause: str
    ) -> None:
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO feedback(id, trace_id, rating, comment, root_cause, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (feedback_id, trace_id, rating, comment, root_cause, utc_now().isoformat()),
            )

    def get_feedback(self, feedback_id: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM feedback WHERE id=?", (feedback_id,)
            ).fetchone()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO conversation_messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, utc_now().isoformat()),
            )

    def recent_messages(self, session_id: str, limit: int = 6) -> list[sqlite3.Row]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT role, content, created_at FROM conversation_messages
                WHERE session_id=? ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def record_bad_case(
        self,
        bad_case_id: str,
        case_id: str,
        question: str,
        expected_intent: str,
        actual_intent: str | None,
        answer: str,
        root_cause: str,
    ) -> None:
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO bad_cases(
                    id, case_id, question, expected_intent, actual_intent,
                    answer, root_cause, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bad_case_id,
                    case_id,
                    question,
                    expected_intent,
                    actual_intent,
                    answer,
                    root_cause,
                    utc_now().isoformat(),
                ),
            )

    def list_bad_cases(self, limit: int = 100) -> list[sqlite3.Row]:
        self.initialize()
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM bad_cases ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()

    @staticmethod
    def parse_json(value: str | None, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    @staticmethod
    def parse_datetime(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

