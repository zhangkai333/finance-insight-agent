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


class SubTask(BaseModel):
    """A bounded unit in the planner output; execution still uses allowlisted tools."""

    id: str
    kind: Literal[
        "financial_query",
        "financial_analysis",
        "annual_report_search",
        "chart_generation",
        "validation",
        "clarification",
    ]
    objective: str
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["planned", "completed", "skipped", "failed"] = "planned"


class TaskPlan(BaseModel):
    plan_id: str
    strategy: Literal["single", "multi_intent", "fusion", "clarification"]
    subtasks: list[SubTask] = Field(min_length=1)
    clarification_question: str | None = None
    planner: str = "deterministic-policy-v1"


class ValidationReport(BaseModel):
    status: Literal["passed", "warning", "failed"]
    checks: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    task_plan: TaskPlan | None = None
    validation: ValidationReport | None = None


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
    demo_mode: bool = False
    store_backend: str
    finance_backend_requested: str = "sqlite"
    finance_backend_effective: str = "sqlite"
    finance_backend_ready: bool = True
    finance_backend_fallback_reason: str | None = None
    rag_backend_requested: str = "sqlite"
    rag_backend_effective: str = "sqlite"
    rag_backend_fallback_reason: str | None = None
    max_concurrent_requests: int = 2
    active_requests: int = 0


class LegacyQueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    document_ids: list[str] | None = None
    session_id: str | None = Field(default=None, max_length=100)
    top_k: int = Field(default=5, ge=1, le=12)


class LegacyQueryResponse(BaseModel):
    trace_id: str
    answer: str
    intent: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    id: str
    name: str
    media_type: str
    chunk_count: int
    created_at: Any


class IngestResponse(DocumentSummary):
    row_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class PdfIngestResponse(BaseModel):
    status: Literal["ingested", "already_ingested"]
    document_id: str | None = None
    source_hash: str
    markdown_path: str
    json_path: str
    facts_written: int = Field(ge=0)
    chunks_written: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    id: str
    trace_id: str
    root_cause: str | None = None
    created_at: Any
