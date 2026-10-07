# 项目合并说明

## 来源与主架构

- 主版本来自 `finance-insight-agent`，运行入口为 `src/finance_insight`。
- 原目标项目的上传、文档管理、CSV 安全统计、Prompt Injection 标记、Trace、Feedback、BadCase 和会话记忆迁移到 `src/finance_insight/legacy`，作为统一 API 的兼容能力实现。
- 根目录不再保留第二套 `app` 运行架构。

## 数据边界

- 主财务事实库：`data/finance_insight.sqlite3`。
- 主 RAG 库：`data/rag.sqlite3`。
- 上传与兼容 API 的运行库：`data/legacy/finagent_runtime.db`。
- 原目标项目数据库：`data/legacy/finagent.db`，只作为历史备份，不由新请求写入。
- `data/samples` 是 synthetic/demo 示例数据，与主项目真实财务数据区分。

## API

- `/v1/*` 使用主财务 Agent，覆盖结构化查询、Python 计算、年报检索、图表、评测和任务接口。
- `/api/v1/*` 保留原项目客户端兼容路径，覆盖上传、文档列表/删除、RAG 问答、Trace、Feedback 和 BadCase。
- 未迁移真实 `.env` 或 API Key；配置模板仅包含空 Key 和示例值。

## 回滚与检查

合并前快照位于目标目录同级的 `金融数据分析agent自动化.pre-merge-backup-20261005-005027`。本次不自动创建 commit，检查 `git diff` 和 `git status` 后再提交。
