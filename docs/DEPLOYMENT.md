# Deployment

## 1. 推荐：Docker Compose 一键部署

```powershell
Copy-Item .env.example .env   # 首次使用；按需修改密码与 LLM Key
docker compose up -d --build
docker compose ps
```

验收入口：

- 工作台：[http://localhost:8000](http://localhost:8000)
- API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)
- 健康检查：[http://localhost:8000/health](http://localhost:8000/health)

Compose 服务：API 8000、MySQL 8.4 3306、Redis 7（仅容器内部 6379）。API 明确使用 `FINANCE_BACKEND=mysql`。

## 2. 首次启动与数据初始化

1. 若 `./data` 中两个便携 SQLite 文件均不存在，API entrypoint 创建公开合成 Demo；
2. 若二者都存在，保留并使用，不覆盖；只有一个时拒绝启动以避免混库；
3. `db/schema.mysql.sql` 初始化 MySQL Schema；
4. API entrypoint 使用业务键 upsert，把便携 SQLite 同步到 MySQL；重复启动幂等；
5. 在线 `FinancialQueryTool` 查询 MySQL。若连接失败且 `MYSQL_FALLBACK_TO_SQLITE=true`，才降级 SQLite，并在 health/trace 中可见。

卷：`./data:/app/data` 保存便携库、图表与 Trace；`mysql_data`、`redis_data` 保存数据库和 AOF。

## 3. 关键环境变量

| 变量 | 默认值/Compose 值 | 作用 |
|---|---|---|
| `FINANCE_BACKEND` | 本地 sqlite / Compose mysql | 在线财务查询后端 |
| `MYSQL_FALLBACK_TO_SQLITE` | true | MySQL 故障时是否降级 |
| `MYSQL_SYNC_FROM_SQLITE` | Compose true | 启动时幂等同步 |
| `MYSQL_HOST/PORT/DATABASE/USER/PASSWORD` | 见 compose | MySQL 连接 |
| `FINANCE_DB` | `data/finance_insight.sqlite3` | 便携数据源/fallback |
| `RAG_DB` | `data/rag.sqlite3` | 年报混合检索库 |
| `REDIS_URL` | Compose `redis://redis:6379/0` | 会话/任务 Store |
| `DEEPSEEK_API_KEY` / `LLM_API_KEY` | 空 | 可选模型 Key |
| `LLM_BASE_URL/MODEL/TIMEOUT_SECONDS` | 见 `.env.example` | OpenAI-compatible 模型 |

不要提交 `.env`，演示密码也必须在真实部署中替换。

## 4. 本地 Python 模式

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,mysql]"
$env:PYTHONPATH = Join-Path $PWD "src"
python scripts/init_demo_data.py
python -m uvicorn finance_insight.api:app --host 127.0.0.1 --port 8000
```

本地默认 SQLite，便于无 Docker 运行；要直连 MySQL，设置 `FINANCE_BACKEND=mysql` 及 MySQL 环境变量。

## 5. 2026-08-27 空卷实测

执行 `docker compose down -v` 后重新 `docker compose up -d --build`：

- API、MySQL、Redis 三服务健康；
- MySQL 自动同步 10 家公司、3 个年度、10 个指标、300 条财务事实；
- `/health` 返回 requested/effective 均为 mysql、ready=true、Store=redis；
- 综合问题成功执行 4 步工具链，读取 MySQL 9 条事实，返回 3 图、4 引用，无 fallback；
- 三个 `/artifacts/*.png` 均返回 200 `image/png`；容器日志无 CJK glyph missing 警告。

## 6. 常用运维命令

```powershell
docker compose logs -f api
docker compose restart api
docker compose down               # 保留卷
docker compose down -v            # 仅在明确重置 MySQL/Redis 数据时使用
```

## 7. 生产部署前检查

更换 Secret；MySQL/Redis 不暴露公网；增加鉴权/RBAC/限流/CORS；图表迁移对象存储并设置 TTL；异步任务迁移外部队列；接入 OpenTelemetry/集中日志；拆分 readiness/liveness；做并发、灾备与恢复演练。
