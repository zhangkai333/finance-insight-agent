from __future__ import annotations

import re
from dataclasses import dataclass

DOMAIN_TERMS = (
    "营业收入",
    "归母净利润",
    "净利润",
    "净资产收益率",
    "经营现金流",
    "主要原因",
    "解释原因",
    "异常变化",
    "同比下降",
    "同比增长",
    "经营风险",
    "业务驱动",
    "市场需求",
    "客户项目",
    "订单变化",
    "研发投入",
    "产能利用",
)

EXPANSIONS = {
    "原因": ("主要原因", "业务驱动", "市场需求", "客户项目"),
    "异常": ("异常变化", "同比下降", "同比增长"),
    "下降": ("同比下降", "主要原因", "市场需求"),
    "增长": ("同比增长", "业务驱动", "客户项目"),
    "营业收入": ("营业收入", "收入变动"),
    "净利润": ("净利润", "利润变动"),
    "风险": ("经营风险",),
}


@dataclass(frozen=True)
class RewrittenQuery:
    original: str
    terms: list[str]
    fts_expression: str


def _safe_term(term: str) -> str:
    return term.replace('"', '""')


def rewrite_financial_query(query: str, *, broaden: bool = False) -> RewrittenQuery:
    """Turn a Chinese sentence into bounded FTS terms.

    SQLite's trigram tokenizer works well for Chinese phrases, but an entire
    natural-language sentence becomes an overly strict MATCH expression. This
    rewriter only emits allowlisted financial phrases joined by OR.
    """
    compact = re.sub(r"\s+", "", query)
    terms: list[str] = [term for term in DOMAIN_TERMS if term in compact]
    for trigger, additions in EXPANSIONS.items():
        if trigger in compact:
            terms.extend(additions)

    if not terms:
        terms = re.findall(r"[\u4e00-\u9fff]{3,8}", compact)[:4]
    if broaden:
        terms.extend(("主要原因", "业务驱动", "市场需求", "客户项目", "经营风险"))

    deduplicated = list(dict.fromkeys(term for term in terms if len(term) >= 3))[:10]
    if not deduplicated:
        deduplicated = ["主要原因"]
    expression = " OR ".join(f'"{_safe_term(term)}"' for term in deduplicated)
    return RewrittenQuery(original=query, terms=deduplicated, fts_expression=expression)
