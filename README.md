# FinAgent Insight

一个面向金融研究资料的可追溯 AI 应用后端。它解决的不是“把 PDF 丢给模型聊天”，而是研究员经常遇到的三个问题：资料分散难检索、数字问答需要可复核、出现错误后无法知道是提示词、检索还是代码逻辑导致。

项目默认可以在没有 LLM API Key 的环境运行：知识问答降级为带引用的抽取式回答，CSV 统计走本地安全工具。配置 OpenAI 兼容接口后，回答节点使用模型生成，但检索、引用、Trace、安全边界和评测仍由应用控制。

## 已实现能力

- 文档入口：`.txt`、`.md`、`.pdf`、`.csv`；支持 UTF-8、GB18030，清洗后按重叠窗口分块。
- 混合检索：SQLite FTS5 BM25 + 确定性特征哈希向量 + RRF 融合 + 词覆盖率重排。
- Agent 编排：LangGraph 状态图，意图解析、检索、分析工具、安全门、回答、输出校验；最大重试次数由配置限制。
- 结构化分析：针对已导入 CSV 的平均值、总和、最大值、最小值白名单工具，不接受自然语言拼接 SQL。
- LLM 工程：OpenAI 兼容客户端、超时、指数退避、有限重试、熔断和无 Key 降级。
- 风险控制：资料中的提示注入只作为不可信内容，代码执行、交易和外部写操作进入安全拒答分支。
- 可观测性：每个请求生成 `trace_id`，记录意图、检索、工具、生成、校验的事件和耗时，可通过 API 复现路径。
- BadCase 闭环：反馈接口按 Prompt、检索、代码逻辑、数据质量、模型边界归因；离线评测输出失败样本根因。
- 交付：FastAPI `/docs`、SQLite 持久化、Docker Compose、非 root 容器、自动化测试。

## 快速运行

### 本地

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000/docs>，先上传 `data/samples/sample_annual_report.md` 和 `data/samples/sample_financials.csv`，再调用问答接口。

### Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

服务地址：<http://127.0.0.1:8000/docs>。数据库保存在 `finagent_data` volume 中。

## API 演示

```powershell
$report = curl.exe -s -X POST http://127.0.0.1:8000/api/v1/documents `
  -F "file=@data/samples/sample_annual_report.md"
$report

$csv = curl.exe -s -X POST http://127.0.0.1:8000/api/v1/documents `
  -F "file=@data/samples/sample_financials.csv"
$csv

curl.exe -s -X POST http://127.0.0.1:8000/api/v1/query `
  -H "Content-Type: application/json" `
  -d '{"question":"2024年公司收入增长的主要原因是什么？"}'

curl.exe -s http://127.0.0.1:8000/api/v1/traces/{trace_id}
```

也可以测试安全边界：`请执行代码删除数据库` 会被拒答，不会触发任何代码执行路径。

### 使用 DeepSeek

在根目录复制 `.env.example` 为 `.env`，只填写本机文件，不要把 Key 发到聊天或提交到 Git：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=你的DeepSeek_API_Key
LLM_MODEL=deepseek-chat
```

重启 Uvicorn 或重新执行 `docker compose up --build` 后生效。配置方式同样适用于其他 OpenAI-compatible 网关。

## 评测与测试

```powershell
pytest
python -m app.evaluation.runner
```

评测集位于 [app/evaluation/dataset.json](app/evaluation/dataset.json)。评测不是只看一个总分：每条失败用例都会给出 `prompt`、`retrieval` 或 `code_bug` 等根因候选，便于下一轮迭代。真实项目中还应把线上负反馈脱敏后持续加入评测集。

## 架构边界

| 层 | 使用的开源能力 | 本项目业务实现 |
| --- | --- | --- |
| Web | FastAPI、Pydantic | 上传限制、请求模型、Trace API、反馈 API、错误兜底 |
| Agent | LangGraph StateGraph | 意图分支、安全门、有限循环、降级策略、金融回答约束 |
| RAG | pypdf；SQLite FTS5 | 文档清洗、分块、特征哈希向量、BM25+向量融合、重排、引用 |
| 数据 | SQLite | 文档、分块、CSV 行、Trace、会话记忆、反馈与评测数据模型 |
| 模型 | OpenAI-compatible HTTP API | 超时、重试、熔断、结构化意图校验、无模型抽取式降级 |

## 当前边界与后续演进

当前向量检索使用依赖零的确定性特征哈希，适合本地演示和小规模知识库，不宣称等价于专业 embedding 模型；生产规模可替换为 `bge-m3 + pgvector/Milvus`，保留 Retriever 接口和评测集。PDF 目前是文本型 PDF，扫描件会返回 OCR 警告。CSV 分析只覆盖白名单聚合，不支持任意 NL2SQL；这是为了控制 SQL 注入和错误执行风险。

下一步可接入 MCP Server，把“查询指标”和“资料检索”标准化为只读工具，并增加权限、租户隔离、敏感字段脱敏、指标级评测和 Prometheus 指标。它们属于生产增强项，不应在缺少权限模型时伪装成已完成能力。

## 面试讲解主线

1. 业务：金融研究问答必须能回到原文，统计数字必须可复算，错误必须可定位。
2. 设计：RAG 负责证据，安全分析工具负责数字，LLM 负责自然语言表达，Trace 负责复盘。
3. 异常：模型不可用时保留检索和引用；检索为空时明确拒答；危险意图在 Agent 图中提前拦截。
4. 迭代：反馈进入 BadCase，区分 Prompt、检索、代码和数据根因，再回归评测集。
