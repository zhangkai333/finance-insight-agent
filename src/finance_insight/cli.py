from __future__ import annotations

import argparse
import json
import sys

from finance_insight.agent import FinanceInsightAgent


def _configure_utf8_stdout() -> None:
    """避免 Windows 默认 GBK 控制台无法输出回答中的 Unicode 字符。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    _configure_utf8_stdout()
    parser = argparse.ArgumentParser(description="上市公司财报智能分析 Agent")
    parser.add_argument("question")
    parser.add_argument("--no-llm", action="store_true", help="禁用真实 LLM，使用确定性规则")
    args = parser.parse_args()
    result = FinanceInsightAgent().run(args.question, use_llm=not args.no_llm)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
