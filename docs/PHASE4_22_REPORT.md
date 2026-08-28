# Phase 4—22 Implementation Report

> 日期：2026-08-27。本文记录主链路已经实现和实际运行的证据，同时明确尚未完成的外部环境验证。Phase 23 简历包装和 Phase 24 模拟面试按当前要求暂不执行。

## Phase 4：Python 调用 LLM API

- **解决的问题**：把模型提供商隔离在统一客户端后面，业务代码不直接拼 HTTP。
- **实现**：`OpenAICompatibleLLMClient` 使用 `httpx` 请求 `/chat/completions`；支持 DeepSeek Key、Base URL、Model、timeout；无 Key 时使用 `DeterministicLLMClient`。
- **实测**：除 MockTransport 协议测试外，真实 DeepSeek smoke 与完整 Agent 链路均成功；服务端返回 `deepseek-v4-flash`，完整任务未 fallback，并返回 4 条引用和 3 张图。5 次小样本基准全部成功。
- **JD 能力**：Python、LLM API、供应商适配、配置安全、重试。
- **面试官可能问**：为什么不用官方 SDK？如何避免 API Key 进入日志？
- **自检问题**：如果从 DeepSeek 切换到另一个 OpenAI-compatible 服务，哪些配置要改、哪些代码不应改？

## Phase 5：Structured Output

- **解决的问题**：自然语言不能直接驱动数据库和工具，必须先变成可校验意图。
- **实现**：Pydantic `QueryIntent` 校验公司、年份、指标、任务类型与 `needs_*`；LLM JSON mode 失败后回退确定性解析；公司和指标二次白名单校验。
- **实测**：合法 JSON、非法/缺失字段、白名单和 parser 标记均有测试。
- **JD 能力**：Prompt Engineering、Pydantic、Structured Output、容错解析。
- **面试官可能问**：JSON mode 为什么仍然需要 Pydantic？
- **自检问题**：模型返回了合法 JSON，但指标写成数据库不存在的字段时，系统在哪一层拦截？

## Phase 6：Function Calling / Tool Calling

- **解决的问题**：定义 LLM 能调用什么，而不是让模型拥有无限制执行能力。
- **实现**：维护工具 schema；实际运行由 LangGraph 根据 `QueryIntent` 调度；工具统一返回 `ToolResult`。
- **实测**：工具参数、状态、错误、延迟和重试次数进入 tool events。
- **JD 能力**：Function Schema、工具契约、安全边界。
- **面试官可能问**：你的项目是原生 function calling 还是 workflow tool calling？为什么？
- **自检问题**：为什么第一版选择“LLM 解析意图 + LangGraph 条件路由”，而不是让 LLM 自由决定任意循环调用？

## Phase 7：SQL Tool

- **解决的问题**：可靠查询财务事实，同时避免模型生成自由 SQL。
- **实现**：`FinancialQueryTool` 根据白名单公司、指标、年度构造参数化 SQL；支持趋势和排名；无数据返回结构化错误。
- **实测**：3 年趋势、2024 排名、数据库缺失故障注入通过；300 条事实可查询。
- **JD 能力**：SQL、数据建模、参数化查询、Agent Tool 安全。
- **面试官可能问**：为什么不做 Text-to-SQL？参数化 SQL 防住了什么？
- **自检问题**：如果要支持“收入大于 50 亿元且 ROE 高于 15%”，你会扩展 QueryIntent 还是放开自由 SQL？

## Phase 8：RAG Tool

- **解决的问题**：结构化指标只能说明“发生了什么”，年报原文用于解释“可能为什么”。
- **实现**：FTS5 + sqlite-vec + RRF Hybrid Retriever；公司/年份过滤；返回文件、页码、chunk；向量层失败回退 FTS5/LIKE。
- **实测**：4,178 个 chunk 和向量一一对应；Hybrid 返回 `retrieval_mode=hybrid_rrf` 与 embedding provider；引用测试通过。
- **JD 能力**：RAG、Embedding 抽象、向量数据库、Hybrid Search、引用溯源。
- **面试官可能问**：SQL 和 RAG 的职责为什么不能互换？RRF 有什么作用？
- **自检问题**：RAG 找到“主要原因”片段，但与财务数值冲突时，最终答案应以哪个来源为准，为什么？

## Phase 9：Python Analysis Tool

- **解决的问题**：财务计算必须确定、可复核，不能依赖 LLM 心算。
- **实现**：按公司和指标分组计算同比、CAGR、异常变化，并保留每个年度的原值、单位和计算值。
- **实测**：凯莱英收入同比 `-23.7%` 与异常数量断言通过。
- **JD 能力**：Python 数据处理、Pandas 类分析思维、业务指标计算。
- **面试官可能问**：异常阈值如何确定？CAGR 在负值或跨零时如何处理？
- **自检问题**：为什么应把同比结果保存成结构化数据，而不是只拼成一段文本？

## Phase 10：Chart Tool

- **解决的问题**：把可信时间序列转换为可交付图表，而不是让模型“描述一个图”。
- **实现**：Matplotlib Agg 后端；每个公司/指标生成 PNG；文件名包含 trace_id；返回绝对路径。
- **实测**：检查 PNG magic bytes；复合问题实际生成 3 张图。
- **JD 能力**：可视化、文件产物管理、后端无头运行。
- **面试官可能问**：并发请求如何避免文件名冲突？生产环境为什么不应长期保存在容器本地盘？
- **自检问题**：图表输入应来自原始 SQL records，还是 Analysis Tool 的 series？为什么？

## Phase 11：LangGraph Agent

- **解决的问题**：多工具任务需要显式节点、边、路由和终止条件。
- **实现**：`parse/query_sql/calculate/retrieve/chart/synthesize` 六节点图；条件边跳过不需要的工具；`MemorySaver` 检查点。
- **实测**：完整问题的工具序列为 SQL → Analysis → RAG → Chart。
- **JD 能力**：LangGraph、Agent Workflow、图编排。
- **面试官可能问**：为什么 LangChain chain 不够？为什么不用开放式 ReAct？
- **自检问题**：如果加入“同业对比”工具，你会把节点放在哪条边之后？

## Phase 12：State / Context / Memory

- **解决的问题**：节点间需要受控传递事实，多轮问题需要有限上下文。
- **实现**：`AgentState` 保存 intent、事实、计算、引用、图表、错误和步数；用 session_id 关联 MemorySaver；后续“再看净利润趋势”可以继承上一轮公司。
- **实测**：两轮 session 集成测试通过，第二轮 parser 带 `session-context`。
- **JD 能力**：状态设计、上下文工程、会话记忆边界。
- **面试官可能问**：短期会话 Memory 与长期用户 Memory 有什么区别？
- **自检问题**：哪些字段应该进入下一轮上下文，哪些不应该，原因是什么？

## Phase 13：多步骤任务执行

- **解决的问题**：复合问题需要先查事实、再计算、再检索原因、最后画图和汇总。
- **实现**：条件路由保证数据依赖顺序；synthesize 只消费已有的 ToolResult，不自行发明事实。
- **实测**：E2E 断言最终答案同时包含 2024、同比、页码和图表。
- **JD 能力**：任务分解、依赖编排、多工具协同。
- **面试官可能问**：为什么 RAG 不能在 SQL 之前随意执行？
- **自检问题**：如果 SQL 失败但 RAG 成功，系统应该返回 success、partial 还是 error？

## Phase 14：Retry / Fallback

- **解决的问题**：外部模型、数据库和向量层并不总是可用。
- **实现**：LLM HTTP 最多 3 次；工具最多 2 次；Hybrid → FTS；LLM → deterministic；Redis → memory；错误写入响应和 Trace。
- **实测**：LLM outage、HTTP 500、数据库缺失和 Redis fallback 测试通过。
- **JD 能力**：可靠性、重试策略、降级、部分成功。
- **面试官可能问**：哪些错误应该重试，哪些不应该？如何避免重试风暴？
- **自检问题**：参数校验失败是否应该重试？为什么？

## Phase 15：FastAPI

- **解决的问题**：将 Agent 封装为其他系统可调用的服务。
- **实现**：健康检查、同步问答、异步任务、任务查询和会话结果接口；Pydantic request/response。
- **实测**：TestClient 集成测试；真实 Uvicorn socket 的 health 和 query 均通过。
- **JD 能力**：FastAPI、REST API、Schema、服务化。
- **面试官可能问**：为什么 Agent 业务错误不一定使用 HTTP 500？
- **自检问题**：422、404、业务 `status=error` 和真正 500 应分别表示什么？

## Phase 16：Redis / 缓存 / 会话

- **解决的问题**：任务状态和会话结果不能只存在请求栈中。
- **实现**：Store 抽象包含 `InMemoryStore` 和 `RedisStore`；设置 TTL；Redis 连接失败时自动 fallback。
- **实测**：真实 Redis 7 已连接；session TTL、API 重启读取、Redis 重启恢复、AOF 和不可用时 fallback 均已验证。多进程/多副本一致性尚未验证。
- **JD 能力**：Redis、缓存抽象、TTL、依赖降级。
- **面试官可能问**：Redis 中的 session 和 LangGraph checkpointer 是同一回事吗？
- **自检问题**：为什么生产多实例不能继续使用 InMemoryStore？

## Phase 17：Docker 部署

- **解决的问题**：固化运行环境并描述 API、Redis、MySQL 的服务关系。
- **实现**：Dockerfile、Compose、健康检查、数据卷、`.env.example`、`.dockerignore`。
- **实测**：Docker Compose 真实重建并启动 API、Redis、MySQL，三服务 healthy；服务 DNS、API health、Redis AOF/TTL、MySQL 卷持久化均通过。
- **JD 能力**：Docker、Compose、环境变量、健康检查。
- **面试官可能问**：build-time、run-time 和 healthcheck 分别验证什么？
- **自检问题**：为什么容器 healthy 仍不等于已完成生产部署、容量规划与灾备验证？

## Phase 18：MCP

- **解决的问题**：让 MCP Client 以标准协议发现并调用财务工具。
- **实现**：stdio MCP Server 暴露 `financial_query` 与 `annual_report_search`。
- **实测**：真实子进程完成 initialize、list_tools、call_tool。
- **JD 能力**：MCP Server、工具暴露、协议集成。
- **面试官可能问**：MCP 与项目内部 Tool Calling 的关系是什么？
- **自检问题**：为什么不应把所有内部函数都直接暴露成 MCP Tool？

## Phase 19：Agent Evaluation

- **解决的问题**：不能只凭主观 demo 判断 Agent 是否有效。
- **实现**：6 条固定问题与 60 条自动标注扩展初稿；输出分类成功率、数值/引用/图表约束及 P50/P95/P99 延迟。
- **实测**：6 条固定集与 60 条自动初稿均全部成功；60 条集平均 61.86 ms、P95 203.53 ms。扩展集仍待人工复核。
- **JD 能力**：Agent Eval、指标拆分、回归基准。
- **面试官可能问**：为什么任务成功率 100% 仍不能证明系统已生产可用？
- **自检问题**：RAG 的 Recall@K 需要什么样的人工标注数据？

## Phase 20：Logging / Trace / Observability

- **解决的问题**：知道一次回答调用了什么、耗时多少、在哪一步失败。
- **实现**：JSONL Trace 记录 timestamp、trace_id、session_id、event、status、latency、error、retry；过滤敏感字段。
- **实测**：Agent 运行后 `data/logs/agent_trace.jsonl` 持续产生事件。
- **JD 能力**：结构化日志、Trace、可观测性、敏感信息处理。
- **面试官可能问**：日志、指标和分布式 Trace 有什么区别？
- **自检问题**：如果 P95 延迟突然上升，你会先按哪个维度拆解？

## Phase 21：测试

- **解决的问题**：保证单工具、集成链路和最终业务结果都能回归。
- **实现**：Unit、Integration、E2E、故障注入、MCP stdio、Hybrid RAG 和 API 测试。
- **实测**：`30 passed`，`compileall`、Compose 配置检查和中文 CLI 冒烟通过。
- **JD 能力**：Pytest、测试分层、Mock、集成测试、回归保障。
- **面试官可能问**：MockTransport 测到了什么、没测到什么？
- **自检问题**：为什么只测 Agent 最终 answer 文本非常脆弱？

## Phase 22：项目文档

- **解决的问题**：让面试官、协作者和未来的自己能够启动、理解、验证和扩展项目。
- **实现**：README、Architecture、API、Data Dictionary、Evaluation、Deployment、ADR 和本报告。
- **实测**：文档中的关键命令对应本轮实际运行记录；未实测能力均明确标记。
- **JD 能力**：工程文档、架构表达、决策记录、边界管理。
- **面试官可能问**：项目最关键的三个设计取舍是什么？
- **自检问题**：你能否不用看代码，在 3 分钟内讲清 SQL、RAG、Python Tool、LangGraph 和 LLM 各自职责？

## 汇总

主链路已经形成：

```text
自然语言
→ Structured Intent
→ 安全 SQL
→ Python 确定性计算
→ Hybrid RAG + 引用
→ Chart
→ LangGraph 编排
→ DeepSeek-compatible 汇总 / deterministic fallback
→ FastAPI / MCP
→ Eval + Trace + Tests
```

完成不等于生产化。当前 Compose API 财务查询已使用 MySQL，SQLite 作为便携数据源与受控 fallback；60 条扩展集仍待人工复核；DeepSeek 5 次基准也不代表生产 SLA。语义 Embedding/Reranker、生产并发与更大规模人工评测继续记录在 `待补充文档.md`。

