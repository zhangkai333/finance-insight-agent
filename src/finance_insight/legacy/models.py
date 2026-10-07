from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class Intent(StrEnum):
    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    UNSUPPORTED = "unsupported"


class RootCause(StrEnum):
    PROMPT = "prompt"
    RETRIEVAL = "retrieval"
    CODE_BUG = "code_bug"
    DATA_QUALITY = "data_quality"
    MODEL_LIMIT = "model_limit"
    UNKNOWN = "unknown"


class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    excerpt: str
    score: float = Field(ge=0, le=1)


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    document_ids: list[str] | None = None
    session_id: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=5, ge=1, le=12)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return " ".join(value.split())


class QueryResponse(BaseModel):
    trace_id: str
    answer: str
    intent: Intent
    citations: list[Citation]
    confidence: float = Field(ge=0, le=1)
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    id: str
    name: str
    media_type: str
    chunk_count: int
    created_at: datetime


class IngestResponse(DocumentSummary):
    row_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    step: str
    status: Literal["started", "success", "error", "fallback"]
    started_at: datetime
    duration_ms: float | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class TraceDetail(BaseModel):
    id: str
    question: str
    session_id: str | None
    status: str
    answer: str | None
    intent: Intent | None
    degraded: bool
    created_at: datetime
    completed_at: datetime | None
    events: list[TraceEvent]


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    id: str
    trace_id: str
    root_cause: RootCause | None = None
    created_at: datetime


class BadCase(BaseModel):
    id: str
    case_id: str
    question: str
    expected_intent: str
    actual_intent: str | None
    answer: str
    root_cause: RootCause
    created_at: datetime

