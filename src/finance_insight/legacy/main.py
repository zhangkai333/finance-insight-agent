import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from finance_insight.legacy.agent.graph import FinancialAgent
from finance_insight.legacy.config import get_settings
from finance_insight.legacy.models import (
    BadCase,
    DocumentSummary,
    FeedbackRequest,
    FeedbackResponse,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    RootCause,
    TraceDetail,
    TraceEvent,
    utc_now,
)
from finance_insight.legacy.rag.ingestion import DocumentIngestor
from finance_insight.legacy.storage import Database

settings = get_settings()
logging.basicConfig(
    level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
database = Database(settings.database_path)
ingestor = DocumentIngestor(database)
agent = FinancialAgent(database, settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize()
    yield


app = FastAPI(
    title="FinAgent Insight API",
    description="金融研究资料问答、CSV 基础分析、Trace 与 BadCase 闭环。",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    database.initialize()
    return {
        "status": "ok",
        "service": settings.app_name,
        "llm_configured": str(agent.llm.configured).lower(),
    }


@app.post("/api/v1/documents", response_model=IngestResponse)
async def upload_document(file: UploadFile = File(...)) -> IngestResponse:
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit"
        )
    try:
        return ingestor.ingest(
            file.filename or "unnamed", content, file.content_type or "application/octet-stream"
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/documents", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    return ingestor.list_documents()


@app.delete("/api/v1/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, object]:
    if not ingestor.delete_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True, "document_id": document_id}


@app.post("/api/v1/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    trace_id = f"tr_{uuid.uuid4().hex}"
    database.create_trace(trace_id, request.question, request.session_id)
    effective_request = request
    if request.session_id:
        history = database.recent_messages(request.session_id)
        if history:
            context = "\n".join(f"{item['role']}: {item['content']}" for item in history)
            effective_request = request.model_copy(
                update={"question": f"历史对话：\n{context}\n\n当前问题：{request.question}"}
            )
    try:
        state = await agent.run(effective_request)
        for event in state.get("events", []):
            database.add_event(trace_id, event)
        database.finish_trace(
            trace_id,
            status="success",
            answer=state.get("answer"),
            intent=state.get("intent"),
            degraded=state.get("degraded", False),
        )
        if request.session_id:
            database.add_message(request.session_id, "user", request.question)
            database.add_message(request.session_id, "assistant", state.get("answer", ""))
        return QueryResponse(
            trace_id=trace_id,
            answer=state.get("answer", ""),
            intent=state["intent"],
            citations=state.get("citations", []),
            confidence=state.get("confidence", 0),
            degraded=state.get("degraded", False),
            warnings=state.get("warnings", []),
        )
    except Exception as error:
        database.add_event(
            trace_id,
            TraceEvent(
                step="request",
                status="error",
                started_at=utc_now(),
                input_summary={"question_length": len(request.question)},
                error=type(error).__name__,
            ),
        )
        database.finish_trace(trace_id, status="error", degraded=True)
        raise HTTPException(
            status_code=500, detail=f"Request failed; trace_id={trace_id}"
        ) from error


@app.get("/api/v1/traces/{trace_id}", response_model=TraceDetail)
def get_trace(trace_id: str) -> TraceDetail:
    row = database.get_trace(trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    events = [
        TraceEvent(
            step=event["step"],
            status=event["status"],
            started_at=event["started_at"],
            duration_ms=event["duration_ms"],
            input_summary=database.parse_json(event["input_summary"], {}),
            output_summary=database.parse_json(event["output_summary"], {}),
            error=event["error"],
        )
        for event in database.get_trace_events(trace_id)
    ]
    return TraceDetail(
        id=row["id"],
        question=row["question"],
        session_id=row["session_id"],
        status=row["status"],
        answer=row["answer"],
        intent=row["intent"],
        degraded=bool(row["degraded"]),
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        events=events,
    )


@app.post("/api/v1/feedback", response_model=FeedbackResponse)
def add_feedback(request: FeedbackRequest) -> FeedbackResponse:
    if database.get_trace(request.trace_id) is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    root_cause = _classify_root_cause(request.comment or "")
    feedback_id = f"fb_{uuid.uuid4().hex}"
    created_at = utc_now()
    database.create_feedback(
        feedback_id, request.trace_id, request.rating, request.comment, root_cause.value
    )
    return FeedbackResponse(
        id=feedback_id, trace_id=request.trace_id, root_cause=root_cause, created_at=created_at
    )


@app.get("/api/v1/bad-cases", response_model=list[BadCase])
def list_bad_cases(limit: int = 100) -> list[BadCase]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return [
        BadCase(
            id=row["id"],
            case_id=row["case_id"],
            question=row["question"],
            expected_intent=row["expected_intent"],
            actual_intent=row["actual_intent"],
            answer=row["answer"],
            root_cause=row["root_cause"],
            created_at=row["created_at"],
        )
        for row in database.list_bad_cases(limit)
    ]


def _classify_root_cause(comment: str) -> RootCause:
    lower = comment.lower()
    if any(term in lower for term in ("prompt", "提示词", "指令")):
        return RootCause.PROMPT
    if any(term in lower for term in ("召回", "检索", "引用", "相关资料")):
        return RootCause.RETRIEVAL
    if any(term in lower for term in ("bug", "报错", "代码", "逻辑")):
        return RootCause.CODE_BUG
    if any(term in lower for term in ("数据", "缺失", "脏")):
        return RootCause.DATA_QUALITY
    if any(term in lower for term in ("模型", "幻觉", "上下文")):
        return RootCause.MODEL_LIMIT
    return RootCause.UNKNOWN
