from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from finance_insight.config import Settings, settings
from finance_insight.resilience import retry_call


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, Any]
    fallback_used: bool = False


class LLMClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse: ...


class OpenAICompatibleLLMClient:
    """DeepSeek/OpenAI-compatible Chat Completions 客户端。密钥只从环境变量读取。"""

    def __init__(
        self,
        config: Settings = settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        if not config.llm_api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY 或 LLM_API_KEY")
        self.base_url = config.llm_base_url.rstrip("/")
        self.api_key = config.llm_api_key
        self.model = config.llm_model
        self.timeout = config.llm_timeout_seconds
        self.transport = transport

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        if response_format:
            body["response_format"] = response_format

        def request() -> httpx.Response:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
                response.raise_for_status()
                return response

        response, _ = retry_call(request, attempts=3, base_delay=0.1)
        payload = response.json()
        return LLMResponse(
            content=payload["choices"][0]["message"]["content"],
            model=payload.get("model", self.model),
            usage=payload.get("usage", {}),
        )


class DeterministicLLMClient:
    """无 API Key 时的本地降级，不编造财务事实。"""

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        last = messages[-1]["content"] if messages else ""
        if response_format:
            return LLMResponse(
                content=json.dumps({"question": last}, ensure_ascii=False),
                model="deterministic-local",
                usage={},
                fallback_used=True,
            )
        return LLMResponse(
            content="本地 deterministic provider 已接管；最终结论由确定性工具结果生成。",
            model="deterministic-local",
            usage={},
            fallback_used=True,
        )


def build_llm_client(
    config: Settings = settings,
    *,
    force_deterministic: bool = False,
) -> LLMClient:
    if not force_deterministic and config.llm_enabled:
        return OpenAICompatibleLLMClient(config)
    return DeterministicLLMClient()
