from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from finance_insight.agent import FinanceInsightAgent
from finance_insight.config import ROOT_DIR, settings
from finance_insight.evaluation import run as run_evaluation
from finance_insight.resilience import ConcurrencyLimiter
from finance_insight.schemas import (
    EvaluationRequest,
    HealthResponse,
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
    version="0.2.0",
    description="上市公司财报智能分析 Agent：MySQL + Python + RAG + 图表 + 可追踪报告",
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/artifacts", StaticFiles(directory=settings.artifact_dir), name="artifacts")

agent = FinanceInsightAgent()
store = build_store(settings.redis_url)
request_limiter = ConcurrencyLimiter(settings.max_concurrent_requests)
executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_requests)


def _public_response(response: QueryResponse) -> QueryResponse:
    """Convert local chart files to same-origin URLs for browser clients.

    The deterministic report includes the generated chart paths as evidence. Replace
    those private container paths in the report too, otherwise browser users would
    see links that only exist inside the API container.
    """
    chart_urls = [f"/artifacts/{Path(path).name}" for path in response.charts]
    answer = response.answer
    for local_path, public_url in zip(response.charts, chart_urls):
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
        store_backend=store.backend,
        finance_backend_requested=settings.finance_backend,
        finance_backend_effective=effective,
        finance_backend_ready=ready,
        finance_backend_fallback_reason=fallback_reason,
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
            "识别任务", "查询结构化财务库", "Python计算", "检索年报",
            "生成图表", "生成有来源报告", "记录工具轨迹", "重试与降级",
        ],
    }


@app.post("/v1/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    try:
        with request_limiter.slot(settings.request_queue_timeout_seconds):
            response = _public_response(
                agent.run(request.question, session_id=request.session_id, use_llm=request.use_llm)
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
