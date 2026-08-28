# Evaluation

## 1. 目标

Agent 评测分别检查意图、工具选择、结构化数值、引用、图表和最终任务状态，以便定位失败来自解析、数据、工具、编排还是生成层。

## 2. 数据集

- `evals/dataset.json`：6 条固定 MVP 回归问题，覆盖问数、趋势、排名、RAG、图表和复合任务。
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

## 4. 2026-08-27 实测结果

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

5 次 API 请求全部成功，服务端返回模型为 `deepseek-v4-flash`，未使用 fallback：

- 成功率：5/5，失败率 0%；
- 延迟：平均 856.98 ms，P50 789.68 ms，P95 1221.35 ms，max 1321.84 ms；
- token：prompt 80、completion 5、合计 85；本轮 cache hit token 为 0；
- 按脚本内 2026-08-27 价格基线估算成本：约 ¥0.00009。

报告：`data/evaluation/deepseek_benchmark.json`。完整 Agent 的真实 DeepSeek smoke 也已成功，返回 4 条引用和 3 张图，记录在 `data/evaluation/deepseek_agent_smoke.json`。

## 5. 测试分层

- Unit：意图、Structured Output、LLM HTTP、重试、Store、MySQL loader import、评测集约束和独立 Tool；
- Integration：LangGraph、FastAPI、MCP stdio、Hybrid RAG、故障注入；
- E2E：完整财务分析问题必须同时返回数值、同比、页码引用和图表。

当前结果：`30 passed`，并且 `compileall` 与 `docker compose config --quiet` 通过。新增测试覆盖工作台 HTML/JS、health backend 字段、同源图表、评测 API 和 MySQL 同步快照。

## 6. 结果解释边界

- 6/6 固定集只能说明当前 MVP 回归链路可复现；
- 60/60 扩展集仍是自动标签，需人工复核问题表述、指标、工具、引用和答案；
- DeepSeek 5 次基准样本太小，不代表生产 SLA、并发上限或长期失败率；
- 后续仍需 RAG chunk 级标签与 Recall@K、MRR、nDCG，以及忠实度/引用正确性人工评审；
- 还需并发、超时、长上下文、异常输入和成本压力测试。

## 7. 运行命令

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
$env:PYTHONUTF8 = "1"
python -m pytest -q
python -m finance_insight.evaluation --dataset evals/dataset.json --output data/evaluation/report.json
python scripts/generate_eval_dataset.py
python -m finance_insight.evaluation --dataset evals/dataset_extended_draft.json --output data/evaluation/report_extended_draft.json
python scripts/benchmark_deepseek.py --requests 5 --output data/evaluation/deepseek_benchmark.json
```

## 8. 人工审核入口

已生成 `evals/human_review_round1.csv` 和 `evals/human_review_round1.evidence.jsonl`，包含 60 条真实 DeepSeek Agent 响应；本轮 60 条均成功且未触发 deterministic fallback。它们只是待审核材料，不能因此改称 gold set。评分字段、证据核对方式、双人抽检和版本冻结规则见 `docs/HUMAN_EVALUATION_GUIDE.md`。

## 9. 工作台评测入口

打开 [http://localhost:8000](http://localhost:8000)，点击“运行评测”。页面通过异步评测 API 执行固定 6 题确定性回归，并展示题数、成功率、工具选择正确率和 P95；该操作默认不消耗 LLM 配额。
