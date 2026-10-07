# FinanceInsight Agent 项目上下文摘要

> 用途：后续继续开发、上下文压缩或交接时，优先读取本文件，再按需查看代码。本文是项目需求和当前状态的工作摘要，不替代代码与测试结果。
> 更新原则：每次完成重要功能、改变数据范围、改变验证结果或改变面试口径后同步更新。

## 1. 用户目标

用户准备面试 AI 应用开发 / Agent 应用开发岗位，目标方向是企业级 Agent、RAG 和数据分析。项目要同时满足：

- 能作为真实可运行的财务分析 Agent 演示，而不是只有概念架构；
- 能覆盖财务分析师的高频重复工作：查数、统计、趋势、同比、排名、异常、归因、报告解释、图表和数据校验；
- 能处理单意图、多意图、模糊意图、归因分析、SQL 与年报融合查询；
- 能展示 Agent 应用岗位关键词：Python、FastAPI、LangGraph、Structured Output、Tool Calling、SQL、RAG、Embedding、BM25/Rerank、评测、Trace、Retry/Fallback、Docker、MySQL/Redis、MCP；
- 新增正常文本型财报时，支持 `PDF → Markdown → LLM 结构化 JSON → 财务库/RAG 库` 自动导入；
- 历史数据继续使用，不重新批量处理旧 PDF，不把无效外部 API 调用伪装成已完成。

### 最新范围约定（2026-10-07，优先于旧优化路线）

- 用户提供的 JD 就是岗位参考，不再查询 BOSS 直聘。
- 以本地正常跑通、核心流程能演示、用户能讲清楚为交付标准；节省 token，不做细粒度调优、大规模复测或新增重型组件。
- 复用旧数据；新增 PDF 保留现有实现，不再复测该功能；不要求用户人工校验，也不开展新一轮人工标注。
- 已有功能与面试讲法保留；以下后续优化建议是可选项，不是当前待办。除非用户提出新任务，不自动继续扩展。

## 2. 业务边界

- 主演示公司：凯莱英；便携数据覆盖约 10 家医药上市公司。
- 当前财务事实覆盖：FY 2022—2024。
- 当前知识库：已有年报文本、页码和引用；研报可以作为后续可选资料，不应与年报事实混为一谈。
- SQL 是财务数字唯一事实源；Python 负责同比、CAGR、趋势和异常；RAG 负责解释性原文和页码；LLM 负责意图理解、结构化抽取建议和自然语言表达。
- LLM 不直接生成未经工具核验的财务数字；不允许开放式自由 SQL。
- 归因回答应使用“可能原因 + 年报证据”，不宣称统计因果识别。

## 3. 当前主链路

```text
用户问题
  → parse（结构化 QueryIntent）
  → planner（受控 TaskPlan）
  → query_sql（白名单、参数化查询）
  → calculate（同比/CAGR/趋势/异常）
  → retrieve（公司/年份过滤的年报 RAG）
  → chart（基于可信序列出图）
  → validate（事实、引用和任务覆盖校验）
  → synthesize（带边界和来源的回答）
```

主要实现位置：

- `src/finance_insight/agent/graph.py`：LangGraph 编排、状态和路由；
- `src/finance_insight/intent_parser.py`、`agent/planner.py`：意图和计划；
- `src/finance_insight/tools/sql_tool.py`：财务事实查询；
- `src/finance_insight/tools/analysis_tool.py`：确定性分析；
- `src/finance_insight/tools/rag_tool.py`、`rag/`：检索、重排和引用；
- `src/finance_insight/agent/validator.py`：数据及引用覆盖校验；
- `src/finance_insight/api.py`：FastAPI、工作台、异步任务和 PDF 接口；
- `src/finance_insight/ingestion/document_pipeline.py`：PDF 按页解析为 Markdown、切片和缓存；
- `src/finance_insight/ingestion/pdf_pipeline.py`：LLM JSON 抽取、白名单/页码/单位校验和入库；
- `src/finance_insight/llm/client.py`：OpenAI-compatible / DeepSeek 客户端；
- `src/finance_insight/evaluation.py`、`evals/`：离线回归评测。

## 4. 数据位置

已有数据继续使用：

```text
data/finance_insight.sqlite3   # 结构化财务事实
data/rag.sqlite3               # 年报 RAG 文档、切片、FTS5
data/samples/                  # 小型演示样本
```

新增 PDF 放入：

```text
data/raw/annual_reports/
```

服务接口：

```text
POST /v1/ingestion/pdf
```

导入产物：

```text
data/processed/pdf_ingestion/<sha256>.md
data/processed/pdf_ingestion/<sha256>.json
data/processed/pdf_ingestion/cache/
```

流程细节：PDF 先按页解析，尽量提取文本和表格为 Markdown；只把与财务数据相关的页发送给 LLM，避免直接把超大 PDF 发给模型；LLM 输出结构化 JSON；程序只接收指标白名单、有效报告年度、合法页码和规范单位，再分别写入财务 SQLite 和 RAG SQLite；同一 SHA-256 幂等跳过。扫描件 OCR、复杂表格逐项准确性和真实 DeepSeek happy path 不属于当前已验收范围。

本地 API Key 只放项目根目录 `.env`，不要提交 Git：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-key
LLM_MODEL=deepseek-chat
```

## 5. 当前验证口径

最近一次本机验证命令及结论，以实际重新执行结果为准：

```powershell
$env:PYTHONPATH="src"
$env:PYTHONUTF8="1"
python -m pytest -q
git diff --check
```

最近一次 pytest：31 项通过。核心 RAG、validator、graph 和财务 Agent 测试文件 Ruff 通过；不是全仓 Ruff 通过。`git diff --check` 无代码空白错误。现有确定性评测报告：固定集 5/6（q6 任务状态不符合预期）、silver 7/7、扩展集 58/60（rag_03、rag_05 缺引用且状态为 partial）。不为追求满分继续调优。自动代理标签不是人工 gold set，不能据此宣称真实用户准确率 100%。

2026-10-07 HTTP smoke：首页、`/docs`、`/health` 返回 200，health 为 ok；查数、趋势、多指标融合、数据校验返回 success，模糊问题按预期 partial 澄清且未执行数据工具。服务地址 `http://127.0.0.1:8000/`，后台启动日志 `data/api-smoke.stdout.log`、`data/api-smoke.stderr.log`。进程可能随重启退出，届时按 README 启动。

已实现且本地主链路可演示：SQLite 财务查询、Python 分析、SQLite FTS5 RAG、LangGraph、FastAPI、工作台、图表、页码引用、工具轨迹、校验、会话/异步任务和降级。

代码或配置已提供、但当前环境不应声称已完成真实联调：DeepSeek API、Chroma/BGE-M3、真实 MySQL、真实 Redis、MCP stdio、Docker runtime、扫描件 OCR。历史报告中的这些结果仅是历史记录，不能作为本轮基线。

## 6. 面试演示顺序

1. `/health`：展示实际财务后端、RAG 后端和 fallback 状态。
2. 查询凯莱英 2024 年营业收入：展示 SQL 事实和单位。
3. 统计凯莱英 2022—2024 年营业收入趋势：展示 Python 计算。
4. 同时查询营业收入和归母净利润：展示多指标计划和分别的 `matched_metric` 引用。
5. 输入“请查询某个公司的情况”：展示模糊意图澄清，不触发盲目查询。
6. 分析营业收入异常并结合年报解释：展示 SQL + 分析 + RAG + 页码。
7. 做收入和归母净利润融合查询：展示 `validation`、`tool_events`、`execution_context`，说明数字与原文各自的事实边界。
8. 最后展示 `/v1/ingestion/pdf` 和 PDF pipeline 代码，说明正常文本型财报的 happy path 及未验收边界。

## 7. 可选后续方向（当前不执行）

1. 真实 DeepSeek 配置下跑一次正常文本型 PDF happy path，并检查生成 JSON、财务库和 RAG 库；API Key 仅本地使用。
2. 为 RAG 增加人工 chunk 标签，评估 Recall@K、MRR、nDCG 和引用忠实度。
3. 完成小规模人工 gold set，补齐多意图、归因、融合和数据校验的财务分析师审核。
4. 补做 MySQL/Redis/Chroma/MCP/Docker 的真实环境 smoke 和并发、超时、成本压测。
5. 生产化补充鉴权、RBAC、租户隔离、敏感数据脱敏、审计和指标级权限。

## 8. 诚实的岗位关键词说明

项目按通用 AI 应用 / Agent 岗位关键词做了映射，但当前没有可复核的 BOSS 直聘职位详情样本，因此不能说做过 BOSS JD 词频统计。面试时应直接展示已运行闭环，再说明可配置增强和下一步联调，不把“代码入口”说成“本机已实测”。

## 9. 继续工作规则

- 先读取本文件、`README.md` 和 `git status`，再决定是否需要深入代码；
- 不重做已有历史 PDF 数据处理，除非用户明确要求；
- 不读取或输出 `.env` 中的密钥；
- 改动前先说明将修改的文件；
- 每次功能完成后更新本文件的验证状态和边界；
- 以测试、实际响应和代码为准，优先修复真实不一致，不为了好看扩大能力声明。
