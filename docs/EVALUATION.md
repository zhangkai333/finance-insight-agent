# Evaluation

## 1. 目标

Agent 评测分别检查意图、工具选择、结构化数值、引用、图表和最终任务状态，以便定位失败来自解析、数据、工具、编排还是生成层。

## 2. 数据集

- `evals/dataset.json`：6 条固定 MVP 回归问题，覆盖问数、趋势、排名、RAG、图表和复合任务。
- `evals/dataset_silver.json`：7 条财务分析代理标签问题，覆盖基础查询、统计、多意图、模糊意图、归因、融合和校验。
- `evals/dataset_extended_draft.json`：60 条自动生成初稿，包括 20 条单点问数、10 条趋势、10 条排名、10 条年报解释、10 条图表任务。

60 条扩展集统一标记 `auto_draft_requires_human_review`。它已可用于程序回归，但尚未经过人工逐条审核，不能称为人工标注 gold set。

## 3. 指标

| 指标 | 定义 |
|---|---|
| `intent_accuracy` | 公司和指标解析是否符合标注 |
| `tool_selection_accuracy` | 实际工具序列是否符合期望 |
| `sql_numeric_exact_match` | 指定关键数值是否与事实库标注匹配 |
| `citation_coverage` | 需要 RAG 的问题是否返回足量引用 |
| `task_success_rate` | 状态、工具、图表、引用、数值等整体约束是否满足 |
| `latency_ms` | average、P50、P95、P99 和 max 端到端延迟 |
| `category_summary` | 按问题类别统计数量、成功率和平均延迟 |

## 4. 结果与证据边界

当前最近一次 pytest 为 31 passed；现有报告：固定集 5/6、silver 集 7/7、扩展初稿 58/60，模式均为 deterministic-fallback。固定 q6 状态为 partial；扩展 rag_03、rag_05 缺少引用且状态为 partial。按用户最新要求，不再为评测满分调优。2026-10-07 另通过 5 条代表性 HTTP 演示问题和首页、Swagger、Health 检查。自动标签不是独立人工 gold set，不能据此宣称真实用户准确率 100%。

以下 4.1—4.3 为 2026-08-27 历史摘录，不代表当前报告内容或本轮外部服务联调结果；当前结果以上段及 JSON 文件为准。

### 4.1 固定 MVP 集

```json
{
  "cases": 6,
  "intent_accuracy": 1.0,
  "tool_selection_accuracy": 1.0,
  "citation_coverage": 1.0,
  "sql_numeric_exact_match": 1.0,
  "task_success_rate": 1.0,
  "latency_ms": {"average": 162.82, "p50": 69.69, "p95": 481.88, "p99": 546.90, "max": 563.15},
  "llm_mode": "deterministic-fallback"
}
```

报告：`data/evaluation/report.json`。

### 4.2 60 条自动标注初稿

```json
{
  "cases": 60,
  "intent_accuracy": 1.0,
  "tool_selection_accuracy": 1.0,
  "citation_coverage": 1.0,
  "sql_numeric_exact_match": 1.0,
  "task_success_rate": 1.0,
  "latency_ms": {"average": 61.86, "p50": 24.62, "p95": 203.53, "p99": 279.41, "max": 286.40},
  "llm_mode": "deterministic-fallback"
}
```

首次运行暴露了“扣非净利润/净利润”“经营现金流率/经营现金流”“净资产收益率/净资产”等重叠别名问题；解析器改为最长具体别名优先后，复跑达到 60/60。报告：`data/evaluation/report_extended_draft.json`。

### 4.3 真实 DeepSeek 小样本基准

历史记录：当时 5 次 API 请求全部成功，服务端返回模型为 `deepseek-v4-flash`，未使用 fallback；本轮没有真实 DeepSeek 请求：

- 成功率：5/5，失败率 0%；
- 延迟：平均 856.98 ms，P50 789.68 ms，P95 1221.35 ms，max 1321.84 ms；
- token：prompt 80、completion 5、合计 85；本轮 cache hit token 为 0；
- 按脚本内 2026-08-27 价格基线估算成本：约 ¥0.00009。

报告：`data/evaluation/deepseek_benchmark.json`。旧版本还记录过一次完整 Agent 的真实 DeepSeek smoke（返回 4 条引用和 3 张图），记录在 `data/evaluation/deepseek_agent_smoke.json`；该记录不是本轮验证结果。

## 5. 测试分层

- Unit：意图、Structured Output、LLM HTTP、重试、Store、MySQL loader import、评测集约束和独立 Tool；
- Integration：LangGraph、FastAPI、MCP stdio、Hybrid RAG、故障注入；
- E2E：完整财务分析问题必须同时返回数值、同比、页码引用和图表。

历史版本曾记录 `30 passed` 与 Compose 配置检查；当前最近一次为 `31 passed`，不同版本和测试收集范围不可直接比较。MCP stdio、Docker runtime、真实 MySQL/Redis、Chroma/BGE-M3 均未在本轮执行。Mock 或静态配置测试不能替代外部服务联调。

## 6. 结果解释边界

- 固定集当前 5/6，只反映有限回归问题的结果；
- 7/7 silver 集是代理标签的定向回归，不是财务分析师独立审定答案；
- 扩展集当前 58/60，仍是自动标签，不能作为独立人工审核结论；用户不要求本轮开展人工复核；
- DeepSeek 5 次基准样本太小，不代表生产 SLA、并发上限或长期失败率；
- 后续仍需 RAG chunk 级标签与 Recall@K、MRR、nDCG，以及忠实度/引用正确性人工评审；
- 还需并发、超时、长上下文、异常输入和成本压力测试。

## 7. 运行命令

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
$env:PYTHONUTF8 = "1"
python -m pytest -q
python -m finance_insight.evaluation --dataset evals/dataset.json --output data/evaluation/report.json
python -m finance_insight.evaluation --dataset evals/dataset_silver.json --output data/evaluation/report_silver.json
python scripts/generate_eval_dataset.py
python -m finance_insight.evaluation --dataset evals/dataset_extended_draft.json --output data/evaluation/report_extended_draft.json
python scripts/benchmark_deepseek.py --requests 5 --output data/evaluation/deepseek_benchmark.json
```

## 8. 人工审核入口

历史产物 `evals/human_review_round1.csv` 和 `evals/human_review_round1.evidence.jsonl` 记录了当时 60 条 DeepSeek Agent 响应；本轮没有重跑，也没有完成人工审核。不能称其为 gold set。审核方式见 `docs/HUMAN_EVALUATION_GUIDE.md`。

## 9. 工作台评测入口

打开 [http://localhost:8000](http://localhost:8000)，点击“运行评测”。页面通过异步评测 API 执行固定 6 题确定性回归，并展示题数、成功率、工具选择正确率和 P95；该操作默认不消耗 LLM 配额。
