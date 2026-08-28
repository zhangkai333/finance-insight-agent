# 迁移到笔记本继续开发

## 推荐思路

把内容分成两条通道：

1. **GitHub 同步代码和文档**：方便后续两台电脑持续 `pull/push`；
2. **私有迁移包同步密钥和本地数据**：通过 U 盘、局域网或可信私有存储传输，绝不提交 Git。

不要复制 `.venv`、`__pycache__`、`.pytest_cache`、Docker 容器层。它们依赖机器路径/平台，笔记本应重新创建。

## 1. 原电脑：先同步代码

按 `docs/OPEN_SOURCE_RELEASE.md` 建议先推到 private GitHub 仓库。只有你确认数据许可和密钥检查都通过后再公开。

## 2. 原电脑：生成私有迁移包

默认只复制两个运行 SQLite 数据库，不包含 `.env` 和原始资料：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_transfer_bundle.ps1 `
  -Destination "E:\FinanceInsightBackup"
```

如果笔记本需要真实 DeepSeek Key，可显式加入 `.env`：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_transfer_bundle.ps1 `
  -Destination "E:\FinanceInsightBackup" -IncludeEnv
```

如果还要继续数据抽取/RAG 建库，且你有权在自己的设备间使用这些资料，可再加：

```powershell
-IncludeSourceDocuments
```

脚本会生成 SHA256 清单。包含 `.env` 或原始资料的包必须保持私有；不要把它放入项目目录，也不要上传 GitHub。

Redis 通常只是会话缓存，不值得迁移。MySQL 当前还不是 API runtime，建议在笔记本重新导入；如果确实要保留其状态，可用 `-IncludeDockerVolumes` 额外导出 MySQL dump 和 Redis RDB。

## 3. 笔记本：安装基础软件

- Git；
- Python 3.11 或 3.12；
- Docker Desktop（需要 Compose/Redis/MySQL 时）；
- 可选：GitHub CLI、VS Code/Codex。

## 4. 笔记本：克隆并重建环境

```powershell
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mysql]"
```

如果没有迁移 `.env`：

```powershell
Copy-Item .env.example .env
# 手工填写自己的 DeepSeek Key 和本地数据库密码
```

如果笔记本只需要公开 Demo、不需要继续使用真实研究数据，可跳过私有包并运行：

```powershell
python scripts/init_demo_data.py
```

## 5. 笔记本：导入私有包

```powershell
powershell -ExecutionPolicy Bypass -File scripts/import_transfer_bundle.ps1 `
  -BundlePath "E:\FinanceInsightBackup\finance-insight-transfer-时间戳" `
  -CopyEnv
```

如果包里没有 `.env`，删除 `-CopyEnv`。只有包中确实包含原始资料且目标目录为空时才加 `-CopySourceDocuments`。

## 6. 验证笔记本环境

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
$env:PYTHONUTF8 = "1"
python -m compileall -q src scripts tests
python -m pytest -q
python -m finance_insight.evaluation `
  --dataset evals/dataset.json `
  --output data/evaluation/report.json
python scripts/smoke_deepseek.py
```

启动 Docker：

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
```

期望 `/health` 至少满足：`status=ok`、`finance_db=true`、`rag_db=true`。配置 Key 后应有 `llm_configured=true`；Compose 正常时 `store_backend=redis`。

## 7. 以后两台电脑如何协作

每次开始工作：

```powershell
git pull --rebase
```

改完并验证后：

```powershell
git status
git add <明确的文件>
git commit -m "说明本次改动"
git push
```

不要用 Git 同步 `.env`、数据库写入状态和第三方原始资料。数据库 schema/导入脚本可以进 Git；运行数据通过私有包或可重复构建流程同步。若两台电脑都修改同一 SQLite 文件，不能靠 Git 合并，应指定一台为数据主副本或重新构建。

