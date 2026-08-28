from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from finance_insight.config import Settings, settings
from finance_insight.llm.client import LLMClient
from finance_insight.schemas import CompanyRef, PeriodRange, QueryIntent
from finance_insight.structured_output import validate_structured

METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("营业收入", "营收", "收入"),
    "net_profit_attributable": ("归母净利润", "净利润", "归属于上市公司股东的净利润"),
    "net_profit_excl_non_recurring": ("扣非净利润", "扣除非经常性损益", "扣非"),
    "operating_cash_flow": ("经营活动现金流", "经营现金流", "经营活动产生的现金流量净额"),
    "roe": ("roe", "净资产收益率"),
    "eps": ("每股收益", "eps"),
    "total_assets": ("总资产",),
    "net_assets": ("净资产",),
    "net_margin": ("净利率", "销售净利率"),
    "operating_cash_margin": ("经营现金流率", "经营现金流/营业收入"),
}


def _company_aliases(db_path: Path) -> dict[str, CompanyRef]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT stock_code, company_name FROM companies").fetchall()
    finally:
        con.close()
    aliases: dict[str, CompanyRef] = {}
    for code, name in rows:
        ref = CompanyRef(stock_code=str(code), company_name=str(name))
        aliases[str(code)] = ref
        aliases[str(name).replace("股份有限公司", "").replace("集团", "")] = ref
    common = {
        "凯莱英": "002821", "百普赛斯": "301080", "迈普医学": "301033",
        "百诚医药": "301096", "泰格医药": "300347", "迪安诊断": "300244",
        "昭衍新药": "603127", "药明康德": "603259", "成都先导": "688222",
        "百克生物": "688276",
    }
    for alias, code in common.items():
        aliases[alias] = aliases[code]
    return aliases


def _years(question: str) -> list[int]:
    values = sorted({int(value) for value in re.findall(r"20(?:1\d|2\d)", question)})
    if values:
        return values if len(values) == 1 else list(range(min(values), max(values) + 1))
    return [2022, 2023, 2024]


def _metrics(question: str) -> list[str]:
    """识别指标，并让更长、更具体的别名覆盖其内部的短别名。

    例如“扣非净利润”不应同时命中“净利润”，“经营现金流率”也不应
    同时命中“经营现金流”。不同文本区间的指标仍可同时返回。
    """
    low = question.lower()
    matches: list[tuple[int, int, str, int]] = []
    for metric_order, (code, words) in enumerate(METRIC_ALIASES.items()):
        for word in words:
            alias = word.lower()
            for match in re.finditer(re.escape(alias), low):
                matches.append((match.start(), match.end(), code, metric_order))

    accepted: list[tuple[int, int, str, int]] = []
    for candidate in sorted(matches, key=lambda item: (-(item[1] - item[0]), item[0], item[3])):
        start, end, _, _ = candidate
        if any(start < accepted_end and accepted_start < end for accepted_start, accepted_end, _, _ in accepted):
            continue
        accepted.append(candidate)

    ordered = sorted(accepted, key=lambda item: (item[0], item[3]))
    return list(dict.fromkeys(code for _, _, code, _ in ordered))


def parse_intent(question: str, config: Settings = settings) -> QueryIntent:
    aliases = _company_aliases(config.finance_db)
    companies: list[CompanyRef] = []
    seen: set[str] = set()
    ranking = any(word in question for word in ("排名", "排行", "最高", "最低", "前十"))
    for alias in sorted(aliases, key=len, reverse=True):
        if alias in question and aliases[alias].stock_code not in seen:
            companies.append(aliases[alias])
            seen.add(aliases[alias].stock_code)
    if not companies and ranking:
        companies = [aliases[code] for code in sorted({ref.stock_code for ref in aliases.values()})]
    if not companies:
        raise ValueError("未识别到可查询公司。当前 MVP 支持 10 家医药上市公司，请使用公司简称或股票代码。")
    low = question.lower()
    metrics = _metrics(question)
    if not metrics:
        metrics = ["revenue"]
    needs_rag = any(word in question for word in ("原因", "解释", "年报", "依据", "为什么", "研报"))
    anomaly = any(word in question for word in ("异常", "波动", "大幅", "显著变化", "下滑", "下降"))
    chart = any(word in question for word in ("图", "可视化", "绘制"))
    calculation = anomaly or any(word in low for word in ("同比", "cagr", "增速", "利润率", "平均")) or len(_years(question)) > 1
    task_type = "ranking" if ranking else (
        "comprehensive_analysis" if needs_rag or anomaly or chart else
        ("trend_analysis" if calculation else "query")
    )
    return QueryIntent(
        question=question, companies=companies, period=PeriodRange(years=_years(question)),
        metrics=metrics, needs_sql=True, needs_calculation=calculation,
        needs_rag=needs_rag, needs_chart=chart, needs_anomaly_detection=anomaly,
        task_type=task_type, confidence=0.92, parser="deterministic-rule-v1",
    )


def parse_intent_with_llm(question: str, llm: LLMClient, config: Settings = settings) -> QueryIntent:
    """用 JSON mode 解析意图，再用 Pydantic 和业务白名单做二次校验。"""
    aliases = _company_aliases(config.finance_db)
    allowed_companies = {
        ref.stock_code: ref.company_name for ref in aliases.values()
    }
    prompt = {
        "question": question,
        "allowed_companies": allowed_companies,
        "allowed_metrics": sorted(METRIC_ALIASES),
        "available_years": [2022, 2023, 2024],
        "required_schema": QueryIntent.model_json_schema(),
        "rules": [
            "只输出 JSON 对象", "公司必须来自 allowed_companies",
            "指标必须来自 allowed_metrics", "不做数值计算",
        ],
    }
    response = llm.chat(
        [
            {"role": "system", "content": "你是财务问数意图解析器，只输出满足 schema 的 JSON。"},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    intent = validate_structured(response.content, QueryIntent)
    if any(company.stock_code not in allowed_companies for company in intent.companies):
        raise ValueError("LLM 返回了白名单外公司")
    if any(metric not in METRIC_ALIASES for metric in intent.metrics):
        raise ValueError("LLM 返回了白名单外指标")
    if any(year not in (2022, 2023, 2024) for year in intent.period.years):
        raise ValueError("LLM 请求了当前数据集外年份")
    intent.parser = f"llm-json:{response.model}"
    return intent
