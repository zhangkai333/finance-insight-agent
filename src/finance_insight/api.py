from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from finance_insight import __version__
from finance_insight.agent import FinanceInsightAgent
from finance_insight.config import settings
from finance_insight.evaluation import run as run_evaluation
from finance_insight.ingestion.pdf_pipeline import PdfFinancialIngestor
from finance_insight.legacy.agent.graph import FinancialAgent
from finance_insight.legacy.config import Settings as LegacySettings
from finance_insight.legacy.models import TraceEvent, utc_now
from finance_insight.legacy.rag.ingestion import DocumentIngestor
from finance_insight.legacy.storage import Database
from finance_insight.resilience import ConcurrencyLimiter
from finance_insight.schemas import (
    DocumentSummary,
    EvaluationRequest,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    IngestResponse,
    LegacyQueryRequest,
    LegacyQueryResponse,
    PdfIngestResponse,
    QueryRequest,
    QueryResponse,
    TaskResponse,
)
from finance_insight.stores import build_store

WEB_DIR = Path(__file__).resolve().parent / "web"
settings.artifact_dir.mkdir(parents=True, exist_ok=True)
settings.eval_output.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="FinanceInsight Agent API",
    version=__version__,
    description="上市公司财报智能分析 Agent：MySQL + Python + RAG + 图表 + 可追踪报告",
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/artifacts", StaticFiles(directory=settings.artifact_dir), name="artifacts")

agent = FinanceInsightAgent()
store = build_store(settings.redis_url)
request_limiter = ConcurrencyLimiter(settings.max_concurrent_requests)
executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_requests)
upload_database = Database(settings.upload_database)
upload_ingestor = DocumentIngestor(upload_database)
pdf_ingestor = PdfFinancialIngestor()
legacy_settings = LegacySettings(
    database_path=settings.upload_database,
    llm_base_url=settings.llm_base_url,
    llm_api_key=settings.llm_api_key or "",
    llm_model=settings.llm_model,
    llm_timeout_seconds=settings.llm_timeout_seconds,
    max_upload_mb=settings.max_upload_mb,
)
legacy_agent = FinancialAgent(upload_database, legacy_settings)
upload_database.initialize()


def _public_response(response: QueryResponse) -> QueryResponse:
    """Convert local chart files to same-origin URLs for browser clients.

    The deterministic report includes the generated chart paths as evidence. Replace
    those private container paths in the report too, otherwise browser users would
    see links that only exist inside the API container.
    """
    chart_urls = [f"/artifacts/{Path(path).name}" for path in response.charts]
    answer = response.answer
    for local_path, public_url in zip(response.charts, chart_urls, strict=True):
        answer = answer.replace(local_path, public_url)
    return response.model_copy(update={"charts": chart_urls, "answer": answer})


@app.get("/", include_in_schema=False)
def workspace() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    ready, effective, fallback_reason = agent.sql.ping()
    return HealthResponse(
        status="ok" if ready and settings.rag_db.exists() else "degraded",
        finance_db=settings.finance_db.exists(),
        rag_db=settings.rag_db.exists(),
        llm_configured=settings.llm_enabled,
        demo_mode=settings.demo_mode,
        store_backend=store.backend,
        finance_backend_requested=settings.finance_backend,
        finance_backend_effective=effective,
        finance_backend_ready=ready,
        finance_backend_fallback_reason=fallback_reason,
        rag_backend_requested=agent.rag.requested_backend,
        rag_backend_effective=agent.rag.effective_backend,
        rag_backend_fallback_reason=agent.rag.backend_initialization_error,
        max_concurrent_requests=settings.max_concurrent_requests,
        active_requests=request_limiter.active,
    )


@app.get("/v1/meta")
def meta() -> dict[str, Any]:
    return {
        "name": "FinanceInsight Agent",
        "version": app.version,
        "available_years": [2022, 2023, 2024],
        "example_questions": [
            "分析凯莱英2022—2024年营业收入、净利润和ROE的变化，如果发现异常年份，结合对应年报分析原因，并生成趋势图和分析报告。",
            "查询2024年营业收入排名",
            "结合年报解释凯莱英2024年净利润下降原因",
        ],
        "pipeline": [
            "识别任务",
            "查询结构化财务库",
            "Python计算",
            "检索年报",
            "生成图表",
            "生成有来源报告",
            "记录工具轨迹",
            "重试与降级",
        ],
    }


@app.post("/v1/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    try:
        with request_limiter.slot(settings.request_queue_timeout_seconds):
            response = _public_response(
                await agent.arun(
                    request.question, session_id=request.session_id, use_llm=request.use_llm
                )
            )
    except TimeoutError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    store.set(f"session:{response.session_id}:last", response.model_dump(mode="json"), 3600)
    return response


def _run_task(task_id: str, request: QueryRequest) -> None:
    store.set(f"task:{task_id}", {"task_id": task_id, "status": "running"}, 3600)
    try:
        with request_limiter.slot(settings.request_queue_timeout_seconds):
            result = _public_response(
                agent.run(request.question, session_id=request.session_id, use_llm=request.use_llm)
            )
        store.set(
            f"task:{task_id}",
            {
                "task_id": task_id,
                "status": "completed" if result.status != "error" else "failed",
                "result": result.model_dump(mode="json"),
            },
            3600,
        )
    except Exception as exc:
        store.set(
            f"task:{task_id}",
            {"task_id": task_id, "status": "failed", "error": str(exc)},
            3600,
        )


@app.post("/v1/tasks", response_model=TaskResponse, status_code=202)
def create_task(request: QueryRequest) -> TaskResponse:
    task_id = str(uuid.uuid4())
    store.set(f"task:{task_id}", {"task_id": task_id, "status": "queued"}, 3600)
    executor.submit(_run_task, task_id, request)
    return TaskResponse(task_id=task_id, status="queued")


@app.get("/v1/tasks/{task_id}")
def task(task_id: str) -> Any:
    value = store.get(f"task:{task_id}")
    if not value:
        raise HTTPException(404, "task not found")
    return value


@app.get("/v1/sessions/{session_id}")
def session(session_id: str) -> Any:
    value = store.get(f"session:{session_id}:last")
    if not value:
        raise HTTPException(404, "session not found")
    return value


def _run_eval_task(task_id: str, request: EvaluationRequest) -> None:
    key = f"evaluation:{task_id}"
    store.set(key, {"task_id": task_id, "status": "running"}, 3600)
    try:
        with request_limiter.slot(settings.request_queue_timeout_seconds):
            output = settings.eval_output.with_name(f"report_{task_id}.json")
            summary = run_evaluation(settings.eval_dataset, output, use_llm=request.use_llm)
        settings.eval_output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        store.set(key, {"task_id": task_id, "status": "completed", "result": summary}, 3600)
    except Exception as exc:
        store.set(key, {"task_id": task_id, "status": "failed", "error": str(exc)}, 3600)


@app.post("/v1/evaluations", response_model=TaskResponse, status_code=202)
def create_evaluation(request: EvaluationRequest) -> TaskResponse:
    if not settings.eval_dataset.exists():
        raise HTTPException(503, f"evaluation dataset missing: {settings.eval_dataset}")
    task_id = str(uuid.uuid4())
    store.set(f"evaluation:{task_id}", {"task_id": task_id, "status": "queued"}, 3600)
    executor.submit(_run_eval_task, task_id, request)
    return TaskResponse(task_id=task_id, status="queued")


@app.get("/v1/evaluations/{task_id}")
def evaluation_task(task_id: str) -> Any:
    value = store.get(f"evaluation:{task_id}")
    if not value:
        raise HTTPException(404, "evaluation task not found")
    return value


@app.get("/v1/evaluation/latest")
def latest_evaluation() -> Any:
    if not settings.eval_output.exists():
        return {"status": "not_run", "message": "尚未运行评测"}
    return json.loads(settings.eval_output.read_text(encoding="utf-8"))


@app.post("/api/v1/documents", response_model=IngestResponse)
async def upload_document(file: UploadFile = File(...)) -> IngestResponse:
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit")
    try:
        return upload_ingestor.ingest(
            file.filename or "unnamed", content, file.content_type or "application/octet-stream"
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/v1/ingestion/pdf", response_model=PdfIngestResponse)
async def ingest_financial_pdf(file: UploadFile = File(...)) -> PdfIngestResponse:
    """Parse a new annual report and persist its Markdown, JSON facts and RAG chunks."""
    filename = file.filename or "unnamed.pdf"
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit")
    try:
        result = pdf_ingestor.ingest(filename, content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"PDF ingestion failed: {type(exc).__name__}: {exc}") from exc
    return PdfIngestResponse(
        status=result.status,
        document_id=result.document_id,
        source_hash=result.source_hash,
        markdown_path=result.markdown_path,
        json_path=result.json_path,
        facts_written=result.facts_written,
        chunks_written=result.chunks_written,
        warnings=result.warnings,
        error=result.error,
    )


@app.get("/api/v1/documents", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    return upload_ingestor.list_documents()


@app.delete("/api/v1/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, object]:
    if not upload_ingestor.delete_document(document_id):
        raise HTTPException(404, "Document not found")
    return {"deleted": True, "document_id": document_id}


@app.post("/api/v1/query", response_model=LegacyQueryResponse)
async def legacy_query(request: LegacyQueryRequest) -> LegacyQueryResponse:
    trace_id = f"tr_{uuid.uuid4().hex}"
    upload_database.create_trace(trace_id, request.question, request.session_id)
    question = request.question
    if request.session_id:
        history = upload_database.recent_messages(request.session_id)
        if history:
            context = "\n".join(f"{item['role']}: {item['content']}" for item in history)
            question = f"历史对话：\n{context}\n\n当前问题：{question}"
    from finance_insight.legacy.models import QueryRequest as LegacyRequest

    try:
        state = await legacy_agent.run(
            LegacyRequest(
                question=question,
                document_ids=request.document_ids,
                session_id=request.session_id,
                top_k=request.top_k,
            )
        )
        for event in state.get("events", []):
            upload_database.add_event(trace_id, event)
        intent = state.get("intent")
        upload_database.finish_trace(
            trace_id,
            status="success",
            answer=state.get("answer"),
            intent=intent,
            degraded=state.get("degraded", False),
        )
        if request.session_id:
            upload_database.add_message(request.session_id, "user", request.question)
            upload_database.add_message(request.session_id, "assistant", state.get("answer", ""))
        return LegacyQueryResponse(
            trace_id=trace_id,
            answer=state.get("answer", ""),
            intent=intent.value if intent else "unsupported",
            citations=[citation.model_dump(mode="json") for citation in state.get("citations", [])],
            confidence=state.get("confidence", 0),
            degraded=state.get("degraded", False),
            warnings=state.get("warnings", []),
        )
    except Exception as exc:
        upload_database.add_event(
            trace_id,
            TraceEvent(
                step="request",
                status="error",
                started_at=utc_now(),
                input_summary={"question_length": len(request.question)},
                error=type(exc).__name__,
            ),
        )
        upload_database.finish_trace(trace_id, status="error", degraded=True)
        raise HTTPException(500, f"Request failed; trace_id={trace_id}") from exc


@app.get("/api/v1/traces/{trace_id}")
def get_trace(trace_id: str) -> dict[str, Any]:
    row = upload_database.get_trace(trace_id)
    if row is None:
        raise HTTPException(404, "Trace not found")
    return {
        "id": row["id"],
        "question": row["question"],
        "session_id": row["session_id"],
        "status": row["status"],
        "answer": row["answer"],
        "intent": row["intent"],
        "degraded": bool(row["degraded"]),
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "events": [
            {
                "step": event["step"],
                "status": event["status"],
                "started_at": event["started_at"],
                "duration_ms": event["duration_ms"],
                "input_summary": upload_database.parse_json(event["input_summary"], {}),
                "output_summary": upload_database.parse_json(event["output_summary"], {}),
                "error": event["error"],
            }
            for event in upload_database.get_trace_events(trace_id)
        ],
    }


@app.post("/api/v1/feedback", response_model=FeedbackResponse)
def add_feedback(request: FeedbackRequest) -> FeedbackResponse:
    if upload_database.get_trace(request.trace_id) is None:
        raise HTTPException(404, "Trace not found")
    comment = (request.comment or "").lower()
    root_cause = "unknown"
    for key, terms in {
        "prompt": ("prompt", "提示词", "指令"),
        "retrieval": ("召回", "检索", "引用"),
        "code_bug": ("bug", "报错", "代码", "逻辑"),
        "data_quality": ("数据", "缺失", "脏"),
        "model_limit": ("模型", "幻觉", "上下文"),
    }.items():
        if any(term in comment for term in terms):
            root_cause = key
            break
    feedback_id = f"fb_{uuid.uuid4().hex}"
    created_at = utc_now()
    upload_database.create_feedback(
        feedback_id, request.trace_id, request.rating, request.comment, root_cause
    )
    return FeedbackResponse(
        id=feedback_id, trace_id=request.trace_id, root_cause=root_cause, created_at=created_at
    )


@app.get("/api/v1/bad-cases")
def list_bad_cases(limit: int = 100) -> list[dict[str, Any]]:
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    return [dict(row) for row in upload_database.list_bad_cases(limit)]
