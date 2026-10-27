# Contributing

感谢参与 FinanceInsight Agent。提交改动前请：

1. Fork 仓库并从 `main` 创建功能分支；
2. 使用 Python 3.11+ 创建独立虚拟环境；
3. 安装开发依赖：`python -m pip install -e ".[dev,production-rag]"`；
4. 不要提交 `.env`、API Key、密码、日志、图表、原始竞赛资料或无再分发许可的 PDF；
5. 运行 `python -m compileall -q src scripts tests` 和 `python -m pytest -q`；
6. PR 中写明动机、主要改动、验证命令和数据兼容性影响。

若改动评测集，请保留旧版本，说明标签修订理由，并区分自动初稿与人工审核 Gold Set。若改动数据库 schema，请同时更新迁移/导入脚本和 `docs/DATA_DICTIONARY.md`。
