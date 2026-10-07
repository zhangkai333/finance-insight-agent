# FinanceInsight Agent 面试演示指南

## 一句话介绍

面向财务分析师的受控多工具 Agent：用结构化财务库回答数字问题，用 Python 算趋势和异常，用年报 RAG 检索经营解释及页码证据，LangGraph 负责路由、校验与可观测性。

## 90 秒介绍

我做的是上市公司财务分析 Agent，帮助分析师完成重复查数、跨年统计和年报证据检索。问题先解析成结构化意图，Planner 组合 SQL、Python 分析、RAG 和图表工具，再经过校验节点汇总回答。数字来自财务库，计算由 Python 完成，解释带年报页码；信息不全时先澄清。核心工程是 LangGraph 状态编排、受控查询、引用校验、失败降级和工具轨迹。凯莱英是主演示公司，已有数据还支持多公司查询与排名。默认 SQLite/FTS5 无 Key 可演示，也预留 DeepSeek、Chroma、MySQL/Redis 等接入。新增财报按 PDF → Markdown → LLM JSON → 财务库和知识库导入。

## 面试抓住这五点

- **Agent**：解释意图解析、Planner、条件路由和图状态如何组合多个工具；本地演示是受控工作流工具调用。
- **DataAgent / Text2SQL**：自然语言转结构化意图，再生成白名单参数化查询。称为受控 NL2SQL，不宣称开放式任意 SQL 生成。
- **企业 RAG**：按页解析、切片、公司/年份过滤、召回、重排、页码引用；默认 FTS5，可选向量与 BM25 融合。
- **可信与工程化**：数字由 SQL 提供、Python 算术、引用覆盖校验、Retry/Fallback、Trace、Eval、FastAPI 同步和异步任务。
- **边界追问**：当前是本地可运行项目；外部组件有接入代码，尚未本轮联调。GraphRAG、多模态 RAG、多 Agent、原生 Function Calling、WebSocket 流式与生产 RBAC 不作为已完成能力。

## 3 分钟架构讲法

1. 输入层：`POST /v1/query` 接收问题、会话和 `use_llm`；`GET /health` 披露实际后端和降级原因。
2. 编排层：`parse → planner → query_sql → calculate → retrieve → chart → validate → synthesize`。条件边按任务计划执行，模糊意图可澄清，不开放任意 SQL 或无限 ReAct。
3. 事实层：SQL 是唯一数值事实源，Python 负责确定性计算；RAG 只提供解释性原文和页码。LLM 负责理解、抽取建议和表达，不负责捏造财务数字。
4. 可靠性：白名单和参数化 SQL、有限重试、fallback、`tool_events`、`validation`、`execution_context`、JSONL trace；引用要区分“文本支持观点”和“数字由 SQL 核对”。
5. 新文档：文本型 PDF 解析为按页 Markdown，切分并缓存，LLM 提议结构化 JSON，经 schema/指标/页码校验后写入财务与 RAG SQLite；可选增量写 Chroma。扫描件 OCR、复杂表格准确性和真实 DeepSeek happy path 未在当前机器验收。

## 演示顺序

启动方法见根目录 README。打开 `/docs`，先调用 `/health`，检查 `finance_backend_effective`、`rag_backend_effective` 和 fallback 原因。下列请求使用 `POST /v1/query`，请求体为 `{"question":"...","use_llm":false}`。

| 顺序 | 问题 | 重点观察 |
|---|---|---|
| 1 | 查询凯莱英2024年营业收入 | SQL 事实、单位、来源 |
| 2 | 统计凯莱英2022到2024年营业收入趋势 | SQL + Python 计算 |
| 3 | 同时查询凯莱英2024年营业收入和归母净利润 | 多指标规划 |
| 4 | 请查询某个公司的情况 | `partial` 澄清，无工具调用 |
| 5 | 分析凯莱英2022到2024年营业收入异常变化并解释原因 | SQL + 分析 + RAG 引用 |
| 6 | 分析凯莱英2022到2024年营业收入和归母净利润变化并结合年报解释原因 | 多意图融合 |
| 7 | 核对凯莱英2024年营业收入数据并结合年报验证 | SQL 数值与文本证据的边界 |

展开响应的 `task_plan`、`tool_events`、`citations`、`validation` 和 `execution_context`。多指标引用会带 `matched_metric`，如果某个指标缺少对应证据，校验节点会返回 citation coverage warning。评测命令见 `docs/EVALUATION.md`，最近 pytest 31 passed，现有报告为固定集 5/6、silver 7/7、扩展初稿 58/60，不能宣称全部通过。2026-10-07 已通过查数、趋势、多指标融合、模糊澄清、数据校验的 HTTP 演示检查；按用户要求停止深入调优。后续继续开发优先读取 `docs/PROJECT_CONTEXT.md`。

## 截图设计与代码对应

以用户最后一张无遮挡截图所要求的 RAG 和文档链路为设计参考；下表只列仓库中可核对的实现，不把图片上不可辨认的节点强行解释为既成能力。

| 能力 | 代码、配置或接口 | 使用方式 |
|---|---|---|
| PDF 文本/表格解析、按页 Markdown | `ingestion/document_pipeline.py` | `pdfplumber` 优先、`pypdf` fallback；页码标记供引用 |
| 切片、缓存、增量去重 | `DocumentCache`、`sentence_chunks` | 默认 800 字、200 overlap；SHA-256、metadata fingerprint |
| LLM 结构化 JSON | `ingestion/pdf_pipeline.py`、`llm/client.py` | 配置 `LLM_BASE_URL/API_KEY/MODEL`；从相关页提议事实 |
| 事实与知识入库 | `PdfFinancialIngestor`、`db/finance_schema.sql`、`db/rag_schema.sql` | `POST /v1/ingestion/pdf`；分别写财务与 RAG SQLite |
| 意图/规划/图状态 | `intent_parser.py`、`agent/planner.py`、`agent/graph.py` | `QueryIntent`、条件边、`MemorySaver` |
| 财务查询与计算 | `tools/sql_tool.py`、`tools/analysis_tool.py` | 指标白名单、参数化 SQL、同比/异常等 |
| 默认 RAG | `tools/rag_tool.py`、`rag/hybrid.py`、`rag/rerank.py` | SQLite FTS5；向量不可用时标记 fallback；词法元数据重排 |
| 可选生产 RAG | `rag/semantic.py`、`rag/bm25.py`、`rag/chroma_hybrid.py` | `RAG_BACKEND=chroma`，配置 embedding Key 并安装 optional 依赖；向量 + BM25 融合 |
| 证据校验/轨迹 | `agent/validator.py`、`observability.py` | `validation`、`tool_events`、JSONL trace |
| HTTP/MCP/评测 | `api.py`、`mcp_server.py`、`evaluation.py`、`evals/` | Swagger 演示；MCP 需安装并实测 stdio；离线评测无需 Key |

## 新 PDF 操作和边界

正常文本型年报可经 `/v1/ingestion/pdf` 上传，大小由 `MAX_UPLOAD_MB` 限制。输入文件可放 `data/raw/annual_reports/`；导入产物在 `data/processed/pdf_ingestion/`，包括 `<sha256>.md`、`<sha256>.json` 和缓存/manifest；事实库是 `data/finance_insight.sqlite3`，RAG 库是 `data/rag.sqlite3`。配置 DeepSeek 只需在本地 `.env` 填 `LLM_BASE_URL=https://api.deepseek.com/v1`、`LLM_API_KEY`、`LLM_MODEL=deepseek-chat`，不把 Key 提交 Git。服务端先解析 PDF，再将财务相关 Markdown 页发给大模型，避免直接上传超大 PDF；模型输出 JSON 后程序过滤白名单、单位、页码并入库。这个过滤不是逐项原文核对，模型误抽取仍可能污染自动入库事实；面试时不能称它为审计级准确性。无有效 LLM Key 时，不应演示新增 PDF 入库成功。

## 高频追问

**为什么不让模型直接答？** 财务数值必须可复核，SQL 与计算工具负责事实和算术，模型负责语言。生产化还需只读账号、权限、审计和事实原文逐项核验。

**为什么不是开放式 ReAct？** 财务任务类型有限，结构化计划和显式条件边易测试、易限制工具权限与成本；复杂任务仍可按需组合 SQL、计算、RAG 和图表。

**RAG 如何防止答非所问？** 公司/年份 metadata 过滤、多候选召回、重排、最多两轮检索、证据分数和引用；默认实际运行 FTS5，Chroma/BGE-M3 路径未在当前机器测出召回增益。后续需要 chunk 级 Recall@K、引用忠实度评测。

**数据校验能到什么程度？** 当前能检查结构化事实和引用是否齐全，不能证明研报观点具有因果性，也不能自动发现 PDF 抽取中的所有错行和错单位；异常归因应说成“可能原因及年报证据”，不是统计因果识别。

**MCP 是什么角色？** 将财务查询和年报搜索暴露给外部 MCP Client；它不是内部 LangGraph 的替代。当前本机没有执行 stdio smoke，演示前要安装依赖并运行 `scripts/mcp_client_demo.py`。

**如何证明质量？** 按意图、工具选择、SQL exact match、引用覆盖、任务成功率和延迟分项看。自动 silver 集只适合回归；不能把 7/7 宣称为真实用户泛化准确率。

## JD 关键词和诚实边界

按用户提供的 JD 对齐，不需要继续查 BOSS 直聘。Python、FastAPI、Pydantic Structured Output、LangGraph、Tool Use、受控 NL2SQL、RAG、Embedding、Vector DB、BM25、Rerank、Eval、Trace、Retry/Fallback、Docker、Redis、MySQL、MCP 都能映射到代码或配置，但不等于全部在本机实测。面试优先讲已演示的财务业务闭环、工具权限边界和证据溯源，外部组件按可选接入描述。
