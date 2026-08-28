import json

import httpx

from finance_insight.config import Settings
from finance_insight.intent_parser import parse_intent_with_llm
from finance_insight.llm.client import LLMResponse, OpenAICompatibleLLMClient


class FakeIntentLLM:
    def chat(self, messages, *, response_format=None):
        payload = {
            "question": "查询凯莱英2024年营业收入",
            "companies": [{"stock_code": "002821", "company_name": "凯莱英医药集团（天津）股份有限公司"}],
            "period": {"years": [2024], "period_code": "FY"},
            "metrics": ["revenue"],
            "needs_sql": True,
            "needs_calculation": False,
            "needs_rag": False,
            "needs_chart": False,
            "needs_anomaly_detection": False,
            "task_type": "query",
            "confidence": 0.95,
            "parser": "fake",
        }
        return LLMResponse(content=json.dumps(payload, ensure_ascii=False), model="fake-json", usage={})


def test_structured_intent_uses_json_mode_and_whitelist():
    intent = parse_intent_with_llm("查询凯莱英2024年营业收入", FakeIntentLLM())
    assert intent.parser == "llm-json:fake-json"
    assert intent.metrics == ["revenue"]


def test_openai_compatible_client_retries_and_sends_deepseek_shape():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500, request=request, json={"error": "temporary"})
        body = json.loads(request.content)
        assert body["model"] == "deepseek-chat"
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            request=request,
            json={"model": "deepseek-chat", "choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 3}},
        )

    config = Settings(llm_api_key="test-secret", llm_base_url="https://api.deepseek.com", llm_model="deepseek-chat")
    client = OpenAICompatibleLLMClient(config, transport=httpx.MockTransport(handler))
    result = client.chat([{"role": "user", "content": "ping"}])
    assert result.content == "OK" and len(calls) == 2
