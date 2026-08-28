from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CompanyRef(BaseModel):
    stock_code: str
    company_name: str


class PeriodRange(BaseModel):
    years: list[int] = Field(min_length=1)
    period_code: Literal["FY"] = "FY"


class QueryIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    companies: list[CompanyRef] = Field(min_length=1)
    period: PeriodRange
    metrics: list[str] = Field(min_length=1)
    needs_sql: bool = True
    needs_calculation: bool = False
    needs_rag: bool = False
    needs_chart: bool = False
    needs_anomaly_detection: bool = False
    task_type: Literal["query", "trend_analysis", "ranking", "comprehensive_analysis"]
    confidence: float = Field(ge=0, le=1)
    parser: str = "deterministic"


class ToolResult(BaseModel):
    tool_name: str
    status: Literal["success", "partial", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    latency_ms: float = 0.0
    fallback_used: bool = False


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    session_id: str | None = None
    use_llm: bool = True


class QueryResponse(BaseModel):
    trace_id: str
    session_id: str
    status: Literal["success", "partial", "error"]
    answer: str
    intent: QueryIntent | None = None
    charts: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    fallback_used: bool = False


class TaskResponse(BaseModel):
    task_id: str
    status: Literal["queued", "running", "completed", "failed"]


class EvaluationRequest(BaseModel):
    use_llm: bool = False


class HealthResponse(BaseModel):
    status: str
    finance_db: bool
    rag_db: bool
    llm_configured: bool
    store_backend: str
    finance_backend_requested: str = "sqlite"
    finance_backend_effective: str = "sqlite"
    finance_backend_ready: bool = True
    finance_backend_fallback_reason: str | None = None
