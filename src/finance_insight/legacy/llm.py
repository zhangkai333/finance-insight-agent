import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ValidationError

from finance_insight.legacy.config import Settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, threshold: int, reset_seconds: int):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= self.reset_seconds:
            self.opened_at = None
            self.failures = 0
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


@dataclass
class LLMResult:
    text: str
    degraded: bool = False


class StructuredIntent(BaseModel):
    intent: str
    reason: str = ""


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.breaker = CircuitBreaker(
            settings.llm_circuit_failure_threshold, settings.llm_circuit_reset_seconds
        )
        self._recent_failures: deque[str] = deque(maxlen=20)

    @property
    def configured(self) -> bool:
        return bool(self.settings.llm_api_key)

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0) -> LLMResult:
        if not self.configured:
            return LLMResult("", degraded=True)
        if not self.breaker.allow_request():
            raise LLMUnavailable("LLM circuit is open")

        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.llm_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    text = data["choices"][0]["message"]["content"]
                    self.breaker.record_success()
                    return LLMResult(text=text)
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
                last_error = error
                self.breaker.record_failure()
                self._recent_failures.append(type(error).__name__)
                if attempt < self.settings.llm_max_retries:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise LLMUnavailable(f"LLM request failed after retries: {last_error}")

    async def classify_intent(self, question: str) -> StructuredIntent | None:
        if not self.configured:
            return None
        result = await self.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Classify the user request. Return JSON only with intent and reason. "
                        "intent must be retrieval, analysis, or unsupported."
                    ),
                },
                {"role": "user", "content": question},
            ]
        )
        try:
            payload = json.loads(result.text)
            return StructuredIntent.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            return None
