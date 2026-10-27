# API Reference

Base URL：`http://localhost:8000`。交互式 OpenAPI 文档位于 [http://localhost:8000/docs](http://localhost:8000/docs)。

## 1. 浏览器工作台与静态资源

- `GET /`：用户输入和结果展示工作台；
- `GET /static/styles.css`、`GET /static/app.js`：前端资源；
- `GET /artifacts/{filename}`：同源返回 Agent 生成的 PNG 图表。

API 响应中的 `charts` 和确定性报告中的图表地址均为 `/artifacts/...`，不会泄露容器内部文件路径。

## 2. Health

### `GET /health`

```json
{
  "status": "ok",
  "finance_db": true,
  "rag_db": true,
  "llm_configured": false,
  "demo_mode": true,
  "store_backend": "memory",
  "finance_backend_requested": "sqlite",
  "finance_backend_effective": "sqlite",
  "finance_backend_ready": true,
  "finance_backend_fallback_reason": null
}
```

`demo_mode=true` indicates the public synthetic dataset. The workbench uses this
field to display the synthetic-data notice.

`requested` 与 `effective` 不同时代表 MySQL 故障后使用了 SQLite fallback；原因同时写入 `finance_backend_fallback_reason`。

`max_concurrent_requests` 默认是 `2`。同步查询和后台任务共享 Agent 并发槽位；槽位满时最多等待 `REQUEST_QUEUE_TIMEOUT_SECONDS`，超时返回 HTTP 429。这样可以控制 DeepSeek/数据库压力，避免请求无限堆积。

## 3. 元数据

### `GET /v1/meta`

返回版本、可用年度、示例问题与能力流水线，供工作台或其他客户端初始化。

## 4. 同步问答

### `POST /v1/query`

```json
{
  "question": "分析凯莱英2022到2024年营业收入趋势",
  "session_id": "optional-session-id",
  "use_llm": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question` | string | 是 | 2—2000 字符 |
| `session_id` | string/null | 否 | 不传则生成 UUID；复用可承接上一轮公司上下文 |
| `use_llm` | boolean | 否 | 默认 true；关闭或模型失败时输出确定性报告 |

响应包含 `trace_id`、`session_id`、`status`、`answer`、`intent`、`charts`、`citations`、`tool_events`、`errors`、`fallback_used`、`evidence_summary` 与 `execution_context`。`evidence_summary` 是有上限的事实/计算/来源职责摘要；`execution_context` 展示本次 requested/effective backend、LLM 状态、fallback、步骤数和递归上限；`tool_events.details` 可查看 SQL backend、记录数、检索模式、embedding provider、异常数与图表数。

状态：`success` 为核心链路成功，`partial` 为有可靠结果但可选步骤降级，`error` 为无法交付核心结果。

## 5. 异步任务和会话

- `POST /v1/tasks`：请求体同 `/v1/query`，返回 202 和 task id；
- `GET /v1/tasks/{task_id}`：查询 queued/running/completed/failed；
- `GET /v1/sessions/{session_id}`：最近一次完整回答。

当前后台任务使用进程内 `ThreadPoolExecutor`；生产多副本应替换为 Celery/RQ 等外部队列。

## 6. 评测接口

- `POST /v1/evaluations`，请求 `{"use_llm": false}`：启动固定 6 题评测；
- `GET /v1/evaluations/{task_id}`：轮询评测任务；
- `GET /v1/evaluation/latest`：最近一次评测摘要。

## 7. 错误约定

- 参数不合法：422；任务/会话不存在：404；评测数据不存在：503；
- Agent 业务失败通常包装在 200 响应的 `status/errors/fallback_used`，让界面能展示可解释降级。

## 8. PowerShell 示例

```powershell
$body = @{ question = "查询凯莱英2024年营业收入"; use_llm = $false } | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/v1/query -Method Post -ContentType application/json -Body $body
```
