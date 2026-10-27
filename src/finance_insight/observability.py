from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def now_ms() -> float:
    return time.perf_counter() * 1000


class JsonlTracer:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / "agent_trace.jsonl"

    def emit(
        self, *, trace_id: str, session_id: str, event: str, status: str, **payload: Any
    ) -> None:
        safe = {
            k: v
            for k, v in payload.items()
            if "key" not in k.lower() and "authorization" not in k.lower()
        }
        item = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "trace_id": trace_id,
            "session_id": session_id,
            "event": event,
            "status": status,
            **safe,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

    @contextmanager
    def span(
        self, *, trace_id: str, session_id: str, event: str, **payload: Any
    ) -> Iterator[dict[str, Any]]:
        started = now_ms()
        context: dict[str, Any] = {}
        try:
            yield context
        except Exception as exc:
            self.emit(
                trace_id=trace_id,
                session_id=session_id,
                event=event,
                status="error",
                latency_ms=round(now_ms() - started, 2),
                error=str(exc),
                **payload,
                **context,
            )
            raise
        else:
            self.emit(
                trace_id=trace_id,
                session_id=session_id,
                event=event,
                status="success",
                latency_ms=round(now_ms() - started, 2),
                **payload,
                **context,
            )
