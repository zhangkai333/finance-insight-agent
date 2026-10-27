from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from statistics import mean

from finance_insight.llm import build_llm_client

PRICING_CNY_PER_MILLION = {
    "deepseek-v4-flash": {
        "cache_hit_input": 0.02,
        "cache_miss_input": 1.0,
        "output": 2.0,
        "concurrency_limit": 2500,
    },
    "deepseek-v4-pro": {
        "cache_hit_input": 0.025,
        "cache_miss_input": 3.0,
        "output": 6.0,
        "concurrency_limit": 500,
    },
}


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def estimate_cost_cny(model: str, usage: dict) -> float | None:
    price = PRICING_CNY_PER_MILLION.get(model)
    if not price:
        return None
    cache_hit = int(usage.get("prompt_cache_hit_tokens", 0) or 0)
    cache_miss = int(usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0)) or 0)
    output = int(usage.get("completion_tokens", 0) or 0)
    return (
        cache_hit * price["cache_hit_input"]
        + cache_miss * price["cache_miss_input"]
        + output * price["output"]
    ) / 1_000_000


def run(requests: int) -> dict:
    client = build_llm_client()
    rows = []
    for index in range(requests):
        started = time.perf_counter()
        try:
            response = client.chat(
                [{"role": "user", "content": f"这是第{index + 1}次连通性测试，请只回复OK"}]
            )
            latency_ms = (time.perf_counter() - started) * 1000
            rows.append(
                {
                    "index": index + 1,
                    "status": "success",
                    "model": response.model,
                    "latency_ms": round(latency_ms, 2),
                    "usage": response.usage,
                    "estimated_cost_cny": estimate_cost_cny(response.model, response.usage),
                    "fallback_used": response.fallback_used,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "index": index + 1,
                    "status": "error",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error": str(exc),
                }
            )
    successful = [row for row in rows if row["status"] == "success"]
    latencies = [row["latency_ms"] for row in successful]
    models = sorted({row["model"] for row in successful})
    total_usage = {
        key: sum(int(row["usage"].get(key, 0) or 0) for row in successful)
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        )
    }
    total_cost = sum(row["estimated_cost_cny"] or 0 for row in successful)
    return {
        "requests": requests,
        "successes": len(successful),
        "failures": requests - len(successful),
        "success_rate": len(successful) / requests,
        "models": models,
        "latency_ms": {
            "average": round(mean(latencies), 2) if latencies else 0,
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2) if latencies else 0,
        },
        "token_usage": total_usage,
        "estimated_cost_cny": round(total_cost, 8),
        "pricing_basis": {
            "as_of": "2026-08-27",
            "unit": "CNY per 1M tokens",
            "source": "DeepSeek API Docs - Models & Pricing",
            "prices": PRICING_CNY_PER_MILLION,
            "note": "估算值；实际账单与峰谷定价以 DeepSeek 控制台为准。",
        },
        "rate_limit_basis": {
            model: PRICING_CNY_PER_MILLION.get(model, {}).get("concurrency_limit")
            for model in models
        },
        "results": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="真实 DeepSeek 延迟、token、成本和失败率小样本基准"
    )
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument(
        "--output", type=Path, default=Path("data/evaluation/deepseek_benchmark.json")
    )
    args = parser.parse_args()
    if args.requests < 1:
        raise SystemExit("--requests 必须大于 0")
    report = run(args.requests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
