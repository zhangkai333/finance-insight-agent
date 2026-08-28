# FinanceInsight Agent：迁移、GitHub 与面试学习手册

> 这份手册面向第一次用 Git、GitHub 和 Codex 继续开发项目的人。建议把它当作本项目的“操作入口”。
>
> 当前基线：2026-08-28，本地 `main` 已有首个提交 `287bbf6 Initial project baseline`，本地测试结果为 `30 passed`。

## 0. 先记住一条总原则

这个项目分成两类东西：

1. **代码和可公开文档**：Python 源码、测试、数据库 schema、Docker 配置、合成 Demo 初始化脚本、架构文档。这些进入 GitHub。
2. **只在本地保存的运行资产**：`.env`、API Key、真实 SQLite 数据库、运行日志、图表、原始竞赛资料和年报 PDF。这些不进入 GitHub。

GitHub 负责同步代码；真实数据需要单独、私下、可校验地迁移。不要把 SQLite 数据库直接放进 Git，也不要把 `.venv` 从一台电脑复制到另一台。

---

## 1. 一次性迁移：公司电脑 → GitHub → 笔记本

### 1.1 公司电脑上先确认状态

在项目根目录打开 PowerShell：

```powershell
cd "C:\Users\admin\Documents\ChatGPT\泰迪杯B题agent应用开发项目"
git status --short --branch
git log --oneline -1
git check-ignore -v .env .venv/ data/ "资料待放入/"
```

应该看到：

- 分支是 `main`；
- 最新提交是 `287bbf6 Initial project baseline`；
- `.env`、`.venv/`、`data/`、`资料待放入/` 被 `.gitignore` 忽略。

如果 `git status` 显示有修改，先不要急着上传，检查：

```powershell
git diff
git diff --stat
```

### 1.2 在 GitHub 网页创建仓库

1. 登录 GitHub，点击新建 Repository。
2. 仓库名可以用：`finance-insight-agent`。
3. 第一次建议选择 **Private**，先用于两台电脑同步。
4. 不要勾选自动创建 README、`.gitignore` 或 License，因为本地已经有这些文件。
5. 创建完成后复制仓库地址，形如：
   `https://github.com/<你的用户名>/finance-insight-agent.git`

### 1.3 把本地代码推送到 GitHub

把下面的占位符替换成你的地址：

```powershell
git remote add origin https://github.com/<你的用户名>/finance-insight-agent.git
git remote -v
git push -u origin main
```

如果 GitHub 要求登录：

- 按浏览器或 Git Credential Manager 的提示登录；
- 如果要求密码，不要填写 GitHub 登录密码，应按 GitHub 当前提示使用浏览器登录或 Personal Access Token；
- 不要把 Token 写进代码、`.env.example` 或聊天记录。

推送后在 GitHub 页面检查文件列表，确认没有：

- `.env`；
- `data/finance_insight.sqlite3`、`data/rag.sqlite3`；
- `资料待放入/`；
- PDF、运行日志、生成图表；
- 任何真实 API Key、密码或数据库连接信息。

### 1.4 如果以后要公开仓库

推荐顺序是：

1. 先保持 Private，在笔记本成功 clone、安装、测试、运行 Demo；
2. 检查 GitHub 文件和提交历史；
3. 确认竞赛资料、年报和研报的再分发权；
4. 再在 GitHub Settings 中改成 Public。

本项目已经提供 `scripts/init_demo_data.py`，公开代码可以用完全虚构的合成数据完成端到端演示，不需要公开真实财务数据库。

---

## 2. 笔记本上继续开发

### 2.1 笔记本需要安装

建议安装：

- Git；
- Python 3.12；
- Codex 桌面应用；
- Docker Desktop（如果要运行 MySQL、Redis 和 Compose 全链路）。

如果只想先学习和运行 Python 版本，Docker 可以稍后安装。

### 2.2 克隆代码并建立全新的 Python 环境

在笔记本 PowerShell 执行：

```powershell
cd "$HOME\Documents"
git clone https://github.com/<你的用户名>/finance-insight-agent.git
cd finance-insight-agent

py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev,mysql]"
Copy-Item .env.example .env
$env:PYTHONPATH = Join-Path $PWD "src"
```

`.env` 只在笔记本本地存在。第一次可以让 `DEEPSEEK_API_KEY` 留空，先使用 deterministic fallback；需要真实 LLM 时，再在本地 `.env` 写入自己的 Key。

### 2.3 先用合成 Demo 验证代码

```powershell
python scripts/init_demo_data.py
python -m pytest -q
```

预期：测试全部通过。然后启动 API：

```powershell
python -m uvicorn finance_insight.api:app --host 127.0.0.1 --port 8000
```

另开一个 PowerShell 窗口测试：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) "src"
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/v1/query `
  -ContentType "application/json" `
  -Body '{"question":"分析凯莱英2022—2024年营业收入、净利润和ROE的变化","use_llm":false}'
```

也可以使用 CLI：

```powershell
python -m finance_insight.cli "查询凯莱英2024年营业收入" --no-llm
```

### 2.4 在笔记本 Codex 中打开项目

在 Codex 桌面应用中选择打开本地项目/文件夹，选择刚刚 clone 的：

```text
C:\Users\<你的用户名>\Documents\finance-insight-agent
```

不同版本的 Codex 界面按钮名称可能不同，但核心要求只有两个：打开的是 Git clone 后的项目根目录，并且终端当前目录也是这个目录。打开后先把下面这句话发给 Codex：

> 请先阅读 README.md、CONTEXT.md、PROJECT_REQUIREMENTS.md、docs/ARCHITECTURE.md 和 docs/API.md，不要修改代码。请用中文说明项目的业务目标、端到端调用链、每个工具的职责、数据边界和当前已知限制，并列出你建议我先学习的 5 个文件。

这样可以先建立上下文，再开始改代码。

---

## 3. 真实数据库和原始资料如何迁移

### 3.1 推荐方案：先只迁移代码，笔记本用合成 Demo

这是最安全、最适合公开 GitHub 和面试准备的方案。真实数据库不是理解代码的必要条件；代码中已经有 schema、导入脚本和 Demo 初始化流程。

### 3.2 如果确实需要公司电脑上的真实数据库

在公司电脑上，把迁移包放到**项目目录之外**，例如移动硬盘或私有加密盘：

```powershell
New-Item -ItemType Directory -Force "D:\private-transfer" | Out-Null
.\scripts\export_transfer_bundle.ps1 -Destination "D:\private-transfer"
```

这个命令默认只复制两个 SQLite 数据库，并生成 SHA256 清单。不要使用 `-IncludeEnv`，除非目标是你自己的私有、安全存储；不要把迁移包上传到 GitHub。

如果还需要原始资料，明确知道资料只能私下使用时才执行：

```powershell
.\scripts\export_transfer_bundle.ps1 `
  -Destination "D:\private-transfer" `
  -IncludeSourceDocuments
```

如果需要把 `.env` 一起迁移，必须知道这会包含 API Key：

```powershell
.\scripts\export_transfer_bundle.ps1 `
  -Destination "D:\private-transfer" `
  -IncludeEnv
```

更推荐在笔记本上重新创建 `.env`，手工填写 Key，而不是复制密钥。

### 3.3 笔记本导入私有迁移包

先 clone 代码、创建 `.venv`，再在项目根目录执行：

```powershell
.\scripts\import_transfer_bundle.ps1 `
  -BundlePath "D:\private-transfer\finance-insight-transfer-<时间戳>"
```

如果迁移包中包含 `.env`，才加 `-CopyEnv`；如果包含原始资料，才加 `-CopySourceDocuments`：

```powershell
.\scripts\import_transfer_bundle.ps1 `
  -BundlePath "D:\private-transfer\finance-insight-transfer-<时间戳>" `
  -CopyEnv `
  -CopySourceDocuments
```

脚本会先校验 SHA256。导入后重新运行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = Join-Path $PWD "src"
python -m pytest -q
```

### 3.4 绝对不要这样做

```powershell
git add -f .env
git add -f data\*.sqlite3
git push
```

如果密钥曾经进入 Git 历史，仅仅删除当前文件是不够的：应立即撤销/轮换 Key，并再处理 Git 历史。对你现在的仓库来说，首个 commit 没有包含这些被忽略文件，当前状态是安全的。

---

## 4. 迁移完成后：笔记本作为唯一开发电脑

公司电脑完成 GitHub 推送和必要的数据导出后，就不再参与开发。以后所有代码修改、测试、提交和推送都在笔记本完成。

### 每次开始工作

```powershell
cd "项目目录"
git switch main
git pull --rebase
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = Join-Path $PWD "src"
```

### 做一个具体优化

```powershell
git switch -c codex/<简短主题>
# 让 Codex 修改代码
python -m pytest -q
# 必要时手动运行 API 或 Docker 验证
git status
git diff
```

### 验证通过后提交并上传

```powershell
git add <明确的文件路径>
git commit -m "说明本次改动"
git push -u origin codex/<简短主题>
```

如果你暂时不熟悉 Pull Request，可以在笔记本直接合并回 `main`；更规范的方式是使用分支并在 GitHub 上创建 PR。

### 关于数据

代码通过 GitHub 同步；SQLite、日志、图表、`.env` 和原始资料只保存在笔记本本地或私有备份中。不要把运行数据库当成代码提交，也不要在多个地方同时修改同一个 SQLite 文件。以后如果笔记本损坏，用 GitHub 恢复代码，用私有备份恢复真实数据，或重新运行 `scripts/init_demo_data.py` 生成合成 Demo。

---

## 5. 用一句话理解项目

**FinanceInsight Agent 是一个面向企业财务分析人员的、带证据和可追踪性的多工具 Agent：LLM 负责理解问题和组织表达，SQL 负责返回可信财务事实，Python 负责计算，RAG 负责返回年报依据，图表工具负责可视化，LangGraph 负责把这些步骤按条件编排起来。**

最重要的设计原则是：**LLM 不是财务事实来源。**

---

## 6. 从用户问题到答案，完整走一遍

用户输入：

> 分析凯莱英 2022—2024 年营业收入、净利润和 ROE 的变化，如果有异常，结合年报解释原因并生成趋势图。

系统的执行链路：

```text
HTTP / CLI / MCP
    ↓
FastAPI 接收 QueryRequest
    ↓
LangGraph Agent 创建 AgentState
    ↓
parse：自然语言 → QueryIntent（公司、年份、指标、任务类型、needs_*）
    ↓
query_sql：只用白名单指标和参数化查询读取财务事实
    ↓
calculate：Python 计算同比、CAGR、异常点
    ↓
retrieve：FTS5 + sqlite-vec 混合检索年报片段和页码
    ↓
chart：根据已验证的时间序列生成 PNG
    ↓
synthesize：LLM 或 deterministic fallback 汇总答案
    ↓
QueryResponse：答案、intent、图表、引用、工具轨迹、降级信息
```

条件路由由 `QueryIntent` 决定：

- 只查数字：SQL；
- 趋势/同比/CAGR：SQL + Python；
- 问“为什么”：SQL + Python + RAG；
- 要图：再加 Chart；
- 综合报告：四类工具全部可能参与。

每个工具输出 `ToolResult`，包含状态、耗时、错误、是否降级和结构化数据。Agent 还会记录 JSONL trace，并对错误工具最多重试 2 次。

---

## 7. 代码阅读顺序

不要一开始从所有文件逐个看。按下面顺序阅读：

1. `README.md`：知道项目要解决什么问题、如何运行；
2. `CONTEXT.md`：知道财务事实、报告期间、统一语义层等领域术语；
3. `src/finance_insight/schemas.py`：理解 `QueryIntent`、`ToolResult`、`QueryResponse`；
4. `src/finance_insight/agent/state.py`：理解 Agent 在节点之间传递什么状态；
5. `src/finance_insight/agent/graph.py`：理解 LangGraph 节点和条件边；
6. `src/finance_insight/intent_parser.py`：理解问题如何变成结构化意图；
7. `src/finance_insight/tools/sql_tool.py`：理解白名单、参数化 SQL 和 SQLite/MySQL fallback；
8. `src/finance_insight/tools/analysis_tool.py`：理解确定性计算；
9. `src/finance_insight/tools/rag_tool.py`、`src/finance_insight/rag/hybrid.py`：理解检索和引用；
10. `src/finance_insight/api.py`：理解 HTTP 接口、异步任务、会话和健康检查；
11. `tests/`：理解系统如何被验证，而不是只看实现；
12. `docs/EVALUATION.md`、`docs/DEPLOYMENT.md`：理解评测和部署边界。

### 每个文件都问自己 4 个问题

1. 输入是什么？
2. 输出是什么？
3. 出错时怎么办？
4. 如何测试它？

这四个问题就是面试时讲代码的通用框架。

---

## 8. 面试时的 90 秒项目介绍

可以先背下面这个版本，再替换成自己的真实经历：

> 我做了一个 FinanceInsight Agent，目标是帮助财务分析人员从上市公司年报中完成“查事实、算趋势、找原因、出图表”的闭环。系统采用 FastAPI 提供接口，LangGraph 编排 Agent 工作流，先把自然语言问题解析成 Pydantic 定义的 QueryIntent，再根据需求路由到参数化 SQL、Python 分析、混合 RAG 和图表工具。为了降低大模型幻觉，LLM 不直接访问数据库，也不负责生成最终财务数值；数字来自 SQL，计算来自 Python，原因分析引用年报页码。系统支持 SQLite 便携运行和 MySQL/Redis/Docker Compose 部署，同时记录工具耗时、错误、重试和 fallback。当前 MVP 已覆盖 10 家公司、FY 2022—2024，30 个测试通过，限制是数据规模、人工评测集和生产级鉴权/并发还需要继续完善。

说完后，面试官通常会追问“为什么这样设计”，再进入下面的技术点。

---

## 9. 高频面试问题与回答思路

### Q1：为什么不用一个 Prompt 让 LLM 直接回答？

因为财务数字要求可核验。让 LLM 直接回答会把事实查询、计算和自然语言生成混在一起，难以控制幻觉，也难以复现。这个项目采用“结构化意图 + 受控工具 + 受控汇总”：LLM 做语言理解和表达，工具做事实和计算。

### Q2：为什么使用 LangGraph？

因为这个任务不是一次 LLM 调用，而是有状态、有条件分支、有失败处理的流程。LangGraph 让 `parse → query_sql → calculate/retrieve/chart → synthesize` 变成显式图，状态集中在 `AgentState`，便于观察、测试和限制循环。

### Q3：如何防止 SQL 注入或模型查到不该查的数据？

模型不能直接执行自由 SQL。指标、公司、年份先进入 Pydantic 结构化对象，再由工具做白名单校验；SQL 使用固定查询模板和参数化占位符。更进一步的生产方案是数据库只读账号、行列权限、审计日志和查询超时。

### Q4：RAG 为什么用混合检索？

关键词检索适合财务术语、指标名和公司专有名词；向量检索适合语义相近但措辞不同的表述。两路召回后用 RRF 融合，且保留公司、年份、页码、chunk_id 和检索模式，方便审计。当前 hashing embedding 是可复现基线，不应包装成生产级语义模型。

### Q5：如果 MySQL、Redis、LLM 或向量检索挂了怎么办？

系统有明确降级边界：MySQL 可回退 SQLite，Redis 可回退内存存储，LLM 可回退 deterministic parser/answer，混合向量检索可回退 FTS5/LIKE。关键不是“永不出错”，而是失败可见、结果不编造，并在 response、health 和 trace 中暴露 fallback。

### Q6：你如何证明 Agent 做得好？

不是只看“回答像不像”，而是分层评测：意图准确率、工具选择准确率、SQL 数值 exact match、引用覆盖率、任务成功率、延迟 P50/P95，再加人工评测。自动生成的扩展集只能叫 draft，必须人工审核后才能作为 gold set。

### Q7：项目现在最明显的不足是什么？

MVP 数据规模有限，人工 gold set 还需冻结，当前 embedding 是 hashing baseline；任务执行仍不是生产级分布式队列，鉴权、权限、并发压测、OCR 和更强 reranker 还没有完成。主动讲限制比把 Demo 说成生产系统更可信。

### Q8：如果让你继续优化，优先做什么？

先做数据和评测闭环：人工审核 60 条问题、补充引用正确性和拒答测试；然后做安全和生产能力：只读数据库账号、鉴权、限流、超时、真正的任务队列和 OpenTelemetry；最后再升级 embedding/reranker。先提高可证明的正确性，再追求模型效果。

### Q9：MCP 在这个项目里解决什么问题？

MCP 把财务查询和年报检索以标准工具协议暴露给外部 Agent 或客户端。它与内部 LangGraph 编排不是同一层：LangGraph 是本项目内部流程，MCP 是对外工具接入边界。

### Q10：你个人真正贡献了什么？

不要只说“用了某某框架”。应按事实说清：你定义了业务边界和数据模型，设计了工具契约和路由规则，实现了降级/重试/观测，补了测试和评测，解决了跨设备迁移和数据保密问题。若某部分由 AI 辅助编写，应诚实说明你如何审查、运行和验证。

---

## 10. 未来 4 周学习和优化路线

### 第 1 周：能独立运行和解释

- 熟悉 Git：clone、pull、branch、commit、push、diff；
- 跑通合成 Demo、CLI、FastAPI 和 pytest；
- 画出自己的系统架构图；
- 能解释 `QueryIntent` 和 `AgentState` 每个字段。

### 第 2 周：掌握数据和工具层

- 学 SQL：JOIN、索引、参数化查询、事务；
- 读懂 `db/schema.sql` 和 `sql_tool.py`；
- 自己新增一个安全的财务指标；
- 为该指标补单元测试、集成测试和一条评测样本。

### 第 3 周：掌握 Agent、RAG 和可靠性

- 解释 LangGraph 节点、条件边、状态和 checkpointer；
- 解释 chunk、embedding、向量召回、FTS5、RRF、引用；
- 人为注入 MySQL/Redis/LLM 失败，观察 fallback 和 trace；
- 比较“LLM 直接回答”和“工具取证后回答”的差异。

### 第 4 周：形成面试作品

- 完成人工评测 gold set 的第一版；
- 给项目补一个真实可展示的优化 PR；
- 录制一次 5 分钟演示；
- 准备 90 秒介绍、5 分钟架构讲解、3 个故障复盘；
- 把 README 中的“已验证/未验证”更新为真实结果。

---

## 11. 建议的优化优先级

### P0：先做正确性和可证明性

- 人工审核并冻结评测集；
- 增加“无数据时明确拒答”的测试；
- 增加引用页码和引用内容一致性测试；
- 为每个工具统一输入/输出/错误契约；
- README 中区分合成数据、真实数据和已验证边界。

### P1：再做生产可靠性

- 数据库只读账号和权限隔离；
- API 鉴权、限流、请求超时和最大问题长度；
- 把线程池任务替换为真正的任务队列；
- 结构化日志、trace_id 贯穿 API、Agent 和工具；
- 并发压测和成本/延迟统计。

### P2：最后做效果增强

- 更强中文 embedding；
- reranker；
- OCR 和表格解析；
- 真实研报独立数据源；
- 更丰富的财务比率和跨公司对比。

---

## 12. 以后让 Codex 帮你改代码的提问模板

每次不要只说“帮我优化一下”，用这个格式：

```text
目标：<我要解决的具体问题>
范围：只允许修改 <文件或模块>
约束：不能改变 <API/数据结构/已有行为>
先做：先阅读 <相关文件>，说明现状和方案，不要立即改代码
实现：方案确认后再修改
验证：运行 <具体测试命令>，补充测试覆盖 <场景>
交付：说明改了哪些文件、为什么改、还有什么风险
```

例如：

```text
目标：给 financial_query 增加“同比变化率”字段。
范围：src/finance_insight/tools/analysis_tool.py 和 tests/unit/。
约束：不改变现有 QueryResponse 字段，不让 LLM 参与计算。
先做：阅读 schemas、analysis_tool 和现有测试，先给出实现方案。
实现：方案确认后再修改。
验证：运行 python -m pytest -q，并新增正数、负数、缺失年份测试。
交付：列出修改文件、计算公式、边界行为和未解决风险。
```

这套提问方式本身就是 Agent 应用开发岗位需要的能力：明确目标、约束边界、拆分任务、验证结果、说明风险。

