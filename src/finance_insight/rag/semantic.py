from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from finance_insight.config import Settings, settings


class OpenAICompatibleEmbedding:
    """OpenAI-compatible embedding client used by the optional production RAG path."""

    def __init__(self, config: Settings = settings):
        if not config.embedding_api_key:
            raise ValueError("未配置 EMBEDDING_API_KEY")
        self.base_url = config.embedding_base_url.rstrip("/")
        self.api_key = config.embedding_api_key
        self.model = config.embedding_model
        self.batch_size = config.embedding_batch_size
        self.concurrency = config.embedding_concurrency
        self.timeout = config.llm_timeout_seconds
        self.name = f"openai-compatible:{self.model}"

    @staticmethod
    def _bounded(text: str) -> str:
        return text[:2000]

    def _request_batch(self, texts: list[str]) -> list[list[float]]:
        body = {"model": self.model, "input": [self._bounded(text) for text in texts]}
        for attempt in range(1, 6):
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
            if response.status_code != 429:
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                ordered = sorted(payload["data"], key=lambda item: item["index"])
                return [item["embedding"] for item in ordered]
            if attempt < 5:
                time.sleep(0.25 * (2 ** (attempt - 1)))
        raise RuntimeError("Embedding API 在 5 次 429 重试后仍不可用")

    def embed(self, text: str) -> list[float]:
        return self._request_batch([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        batches = [texts[index:index + self.batch_size] for index in range(0, len(texts), self.batch_size)]
        if not batches:
            return []
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            results = list(executor.map(self._request_batch, batches))
        return [embedding for batch in results for embedding in batch]
