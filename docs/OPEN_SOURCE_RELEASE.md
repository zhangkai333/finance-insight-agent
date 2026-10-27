# GitHub 开源发布指南

## 1. 推荐策略：先私有迁移，再审核后公开

当前仓库代码可开源，但原始竞赛资料、年报/研报、RAG 原文切片和部分派生数据库的再分发权尚未确认。最稳妥的顺序是：

1. 先创建 **Private** GitHub 仓库，用于代码备份和笔记本同步；
2. `.env`、原始资料和本地迁移包始终不提交；
3. 完成 `docs/DATA_LICENSE.md` 所列数据授权核对；
4. 做密钥与大文件检查；
5. 再把仓库改为 Public。

## 2. 发布前本地检查

```powershell
git status --short
git check-ignore -v .env "资料待放入" data/artifacts data/logs

# 查看准备提交的文件；第一次可先全部加入暂存区再检查
git add .
git status --short
git diff --cached --stat

# 如果发现不该提交的文件，只取消暂存，不删除本地文件
git restore --staged -- "路径"
```

重点确认：

- `.env` 未出现在暂存区；
- `资料待放入/` 和 PDF 未出现；
- 未提交日志、生成图表和本地迁移包；
- `.env.example` 没有真实 Key/密码；
- 两个运行 SQLite 未提交；公开用户通过 `scripts/init_demo_data.py` 自行生成合成 Demo。

## 3. 第一次提交和推送

先在 GitHub 网页创建一个空仓库。不要勾选自动创建 README、`.gitignore` 或 License，因为本地已有这些文件。然后在本地执行：

```powershell
git branch -M main
git add .
git status --short
git commit -m "Initial open-source release"
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

如果使用 GitHub CLI，也可以在检查并提交后执行：

```powershell
gh auth login
gh repo create <仓库名> --private --source=. --remote=origin --push
```

建议第一次创建为 private；确认 GitHub 页面没有敏感文件后，再在仓库 Settings 中改为 public。

## 4. 让别人下载后能用

公开仓库已包含 `scripts/init_demo_data.py`，无需上传真实 SQLite 或第三方原文。脚本生成 300 条完全虚构的财务事实、10 篇原创演示说明及 FTS5/sqlite-vec 索引；所有演示记录均标记为 `synthetic_demo_only`。它不会默认覆盖已有数据库。

克隆者的典型流程：

```powershell
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\start-demo.ps1
```

Docker 会在命名卷中缺少两个数据库时自动执行相同初始化，因此无需先手工生成：

```powershell
Copy-Item .env.example .env
# DeepSeek Key 可留空；留空时使用 deterministic fallback
docker compose up -d --build
Invoke-RestMethod http://127.0.0.1:8000/health
```

真实数据仍采用“用户合法获取后自行构建”或私有迁移包方式，不进入公开 Git 历史。

## 5. GitHub Actions

`.github/workflows/ci.yml` 在 push/PR 时安装锁定范围内的依赖、执行 Ruff、初始化合成 Demo，并运行完整测试集。测试自身还会在临时目录创建隔离 Demo，不读取维护者的真实数据库或 Key。

## 6. 发布版本

首个公开版本建议打 `v0.1.0` 标签，并在 Release Notes 中明确：

- 这是工程化 MVP，不是投资建议系统；
- Docker Compose 已验证 MySQL runtime、Redis 会话、MCP stdio、SQLite 向量 RAG 和 Chroma hashing/BM25；
- 哪些数据包含在发布中、其许可证是什么；
- DeepSeek Key 由用户自行提供；
- 已知限制与下一阶段路线。
