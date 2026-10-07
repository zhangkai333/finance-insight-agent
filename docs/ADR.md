# Architecture Decision Records

## ADR-001：LLM 不生成自由 SQL

- **状态**：Accepted
- **决策**：LLM 只输出公司、年份、指标和任务类型；SQL Tool 根据白名单参数构造参数化 SQL。
- **理由**：降低 SQL 注入、幻觉字段、越权查询和不可复现风险。
- **代价**：可支持的问题受指标目录与 QueryIntent 限制；复杂查询需要扩展工具 schema。

## ADR-002：先用 SQLite 跑通，保留 MySQL 目标 Schema

- **状态**：Accepted for MVP
- **决策**：本机 E2E 使用 SQLite；同时维护 MySQL 8 Schema 和导入脚本。
- **理由**：SQLite 无服务依赖、便于面试演示和测试；MySQL 体现生产演进方向。
- **代价**：MySQL 8 方言、事务、导入、双后端切换和 API 查询回归已完成；Compose runtime 默认使用 MySQL，SQLite 保留为便携数据源与受控 fallback。它仍不是完整生产系统，尚需连接池、并发、权限和灾备治理。

## ADR-003：LangGraph 使用显式固定工作流，而不是开放式 ReAct 循环

- **状态**：Accepted
- **决策**：固定 `parse → query → calculate/retrieve/chart → synthesize`，用条件边裁剪不需要的节点。
- **理由**：财务场景重视可解释、可测试、可限制；固定工作流比开放式循环更适合第一版。
- **代价**：对完全未知的新工具和动态计划适应较弱；后续可以增加 planner 子图而不是放开无限循环。

## ADR-004：ToolResult 作为统一工具契约

- **状态**：Accepted
- **决策**：所有工具返回 `status/data/citations/error/latency_ms/fallback_used`。
- **理由**：Agent 不需要知道每个工具的异常形式，API、Trace、Eval 也能统一消费。
- **代价**：工具特有细节必须放入 `data`，需要维护字段文档。

## ADR-005：RAG 采用 FTS5 + sqlite-vec + RRF

- **状态**：Accepted as baseline
- **决策**：词法与向量候选分开召回，再做 Reciprocal Rank Fusion；失败回退 FTS5。
- **理由**：一套本地文件即可复现实测词法、向量库、融合和 fallback，避免外部向量服务成为阻塞项。
- **代价**：当前字符 hashing embedding 语义能力有限；需要 BGE/托管 embedding 和 Reranker 强化。

## ADR-006：DeepSeek 使用 OpenAI-compatible 自建客户端

- **状态**：Accepted
- **决策**：使用 `httpx` 调用 `/chat/completions`，通过环境变量配置 Base URL、Model 和 Key。
- **理由**：减少 SDK 耦合，便于 MockTransport、重试、超时和替换兼容提供商。
- **代价**：需要自行跟踪提供商模型 ID 和协议变化。默认配置仍可通过 `LLM_MODEL` 覆盖；2026-08-27 真实调用返回模型为 `deepseek-v4-flash`。

## ADR-007：Redis 不可用时回退内存

- **状态**：Accepted for development
- **决策**：Store 抽象优先 Redis，连接失败使用 InMemoryStore。
- **理由**：本地开发不被 Redis 服务阻塞，同时保留生产存储接口。
- **代价**：内存后端不跨进程、不持久化；生产环境必须启用 Redis 并设置可观测告警。

## ADR-008：异步任务先用 ThreadPoolExecutor

- **状态**：Accepted for MVP
- **决策**：`POST /v1/tasks` 将 Agent 任务提交到进程内线程池。
- **理由**：用最小依赖验证 API 的 queued/running/completed 状态链路。
- **代价**：服务重启会丢任务，多实例不共享队列，不能承担生产任务系统职责。

