# FinanceInsight Agent：后续四项优化路线

# 第六步：按照固定的四项优先级继续优化

> 这四项是后续开发主线。笔记本 Codex 必须先核实现状，再实施，不能把已经存在的能力重新开发一遍。

## 当前状态校正

截至 **2026-08-28**，四项工作的真实状态是：

| 优先级 | 目标 | 当前状态 | 后续正确做法 |
|---|---|---|---|
| P1 | 人工审核 60 条评测问题 | **审核字段已填写 60/60**；当前校验被 `chart_correct` 的非法值阻塞 | 修正趋势题为 `NA`、图表题按技术核对填写 `0/1`，重新校验后冻结为 Gold Set |
| P2 | API 支持 SQLite/MySQL 切换 | **核心能力已经实现**；`FINANCE_BACKEND=sqlite/mysql`、MySQL 查询和 SQLite fallback 已存在 | 先验收双后端一致性，再补连接池、故障演练、并发和测试，不能重复造一套 |
| P3 | 面向评委的交互页面 | **基础工作台已经实现**；已有问题输入、报告、图表、引用、意图、工具轨迹和评测入口 | 做评委视角的视觉、交互、状态反馈和演示流程增强 |
| P4 | RAG 对比实验 | **尚未系统完成** | 建立统一实验集，比较 FTS5、hashing vector、语义 Embedding、Hybrid、Hybrid + Reranker |

---

## 优先级 1：完成 60 条人工评测审核

这是最先开展的任务，也是提高项目可信度最快的一步。

### 使用的文件

```text
evals/human_review_round1.csv
evals/human_review_round1.evidence.jsonl
docs/HUMAN_EVALUATION_GUIDE.md
```

`human_review_round1.csv` 和证据文件属于私人工作数据，不上传 GitHub。笔记本接管时，需要从 `FinanceInsight-人工评测审核文件.zip` 解压并放入项目的 `evals` 目录。

### 每条问题至少检查

- 问题表达是否自然，是否像真实用户会问的问题；
- 公司名称、股票代码和公司标签是否正确；
- 财务指标名称、口径和年份是否正确；
- 期望调用的工具是否合理；
- SQL 返回和最终回答中的数值是否正确；
- 趋势、同比、CAGR、异常判断是否按确定性公式计算；
- RAG 引用是否来自正确公司、年份、页码和文本；
- 引用内容是否真的支持回答中的结论；
- 最终回答是否存在无依据补充或过度推断；
- 无数据或证据不足时，系统是否明确说明限制，而不是编造答案。

### 需要填写的主要字段

```text
intent_correct
tool_correct
numeric_correct
citation_relevant_1_to_5
citation_supports_claim
chart_correct
answer_faithfulness_1_to_5
answer_completeness_1_to_5
question_naturalness_1_to_5
review_status
reviewer
review_notes
```

### 完成标准

- 60 条均不再是 `auto_draft_requires_human_review`；
- 每条都有审核人、审核状态和必要备注；
- 对错误标签进行修订并保留修改理由；
- 形成正式的人工复核 Gold Set；
- 重新运行自动评测；
- 输出自动指标、人工指标、失败案例分类和修复建议；
- 选择典型失败案例，记录修复前后结果，供比赛报告和答辩使用。

### 交付物

建议让笔记本 Codex 在不泄露私人原始内容的前提下生成：

```text
docs/EVALUATION_GOLDSET_REPORT.md
docs/EVALUATION_FAILURE_ANALYSIS.md
docs/EVALUATION_BEFORE_AFTER.md
```

---

## 优先级 2：验收并补强 SQLite/MySQL 双数据源

项目已经支持：

```env
FINANCE_BACKEND=sqlite
```

或：

```env
FINANCE_BACKEND=mysql
```

因此后续任务不是“从零实现切换”，而是证明它可靠、行为一致、失败可观察。

### 验收内容

- 相同问题在 SQLite 和 MySQL 下返回相同的公司、年份、指标和数值；
- `/health` 正确展示 requested backend、effective backend 和 fallback 原因；
- MySQL 正常时确实使用 MySQL，而不是表面配置后仍查询 SQLite；
- MySQL 不可用时，按配置决定显式失败或降级 SQLite；
- fallback 必须出现在 health、response 或 trace 中，不能静默发生；
- 导入脚本重复执行应幂等，不产生重复事实；
- 增加缺表、连接失败、超时、错误密码和数据不一致测试；
- 评估连接池、并发查询、只读账号、事务和超时设置。

### 完成标准

- 有 SQLite/MySQL 同问题回归测试；
- 有故障注入和 fallback 测试；
- 有双后端结果一致性报告；
- README 和部署文档中的说法与真实测试结果一致；
- 可以在答辩时准确描述：

> 本地便携演示默认使用 SQLite；Docker Compose 部署使用 MySQL；系统支持显式数据源切换，并在 MySQL 故障时提供可观察、可配置的 SQLite 降级能力。

---

## 优先级 3：升级面向评委的交互展示台

现有工作台已经有基础功能，后续重点是把它从“开发者页面”优化成“评委一眼看懂的 Agent 演示页面”。

### 建议的完整交互链路

```text
问题输入
→ 结构化意图
→ Agent 当前步骤/工具执行状态
→ 财务指标表
→ 趋势与异常分析
→ 年报引用卡片
→ 趋势图
→ 最终分析报告
```

### 重点优化项

- 提供 3—6 个一键示例问题；
- 实时或分阶段展示 Agent 步骤，不只在结束后一次性显示；
- 明确区分“事实数据”“确定性计算”“年报证据”“LLM 总结”；
- 财务指标表展示单位、年份、公司和数据来源；
- 引用卡片展示公司、年度、页码、原文摘要和检索方式；
- 图表支持清楚的标题、单位、图例和异常点标记；
- 显示当前使用 SQLite 还是 MySQL、是否启用 LLM、是否发生 fallback；
- 增加 loading、失败、无数据、证据不足和重试状态；
- 准备一条 3—5 分钟固定演示流程；
- 做基本响应式布局，确保笔记本投屏时可读。

### 完成标准

- 第一次接触项目的人可以不读 README 就理解输入、执行步骤、证据和结论；
- 至少有一个“综合分析问题”完整展示 SQL、分析、RAG、图表和报告；
- 错误与降级状态对用户可见；
- 展示台改动有自动化测试或最少的回归检查清单；
- 保存答辩截图和演示脚本。

---

## 优先级 4：补充 RAG 对比实验

比较以下方案：

1. 纯 FTS5；
2. 当前 hashing vector；
3. 真正的中文语义 Embedding；
4. FTS5 + Embedding Hybrid；
5. Hybrid + Reranker。

### 实验必须保持一致的条件

- 使用同一份人工审核后的查询集；
- 使用同一份文档切片和元数据过滤规则；
- 使用相同的 `top_k` 或明确记录差异；
- 固定随机种子和版本；
- 将离线索引耗时与在线查询耗时分开；
- 记录模型名称、维度、设备、调用方式和成本；
- 不把 hashing vector 描述成真正的语义 Embedding。

### 建议比较指标

- Recall@K；
- MRR 或 nDCG@K；
- 引用相关率；
- 引用是否支持最终结论；
- 最终回答忠实度与完整度；
- P50/P95 检索延迟；
- 建索引时间与存储占用；
- API 调用成本或本地计算成本；
- 无命中、错公司、错年份、错页码等失败类型。

### 完成标准

- 有可重复执行的实验脚本，而不是手工挑选几个结果；
- 原始实验结果使用 JSON/CSV 保存；
- 生成对比表、图表和结论；
- 说明最终方案为什么被选择，以及效果、延迟、成本之间的取舍；
- 将结论写入比赛报告、README 和面试材料，但只陈述真实运行过的结果。

---

## 四项工作的执行顺序

不要同时铺开四项工作。推荐顺序：

```text
人工审核 60 条
→ 冻结 Gold Set
→ 用 Gold Set 建立当前基线
→ 验收 SQLite/MySQL 双后端
→ 优化评委展示台
→ 运行五组 RAG 对比实验
→ 分析失败案例
→ 修复关键问题
→ 重新评测并形成修复前后对比
→ 更新 README、比赛报告和面试材料
```

原因是：没有人工确认的 Gold Set，后续 RAG 实验和修复前后对比都缺少可信基准。

## 每个优先级统一遵守的开发规则

- 一次只处理一个明确子任务；
- 修改前创建 `codex/` 开头的分支；
- 先记录基线，再修改代码；
- 优先补测试，再改实现；
- 每次完成后运行相关测试和完整回归；
- 检查 `git diff` 与 `git status`；
- 不提交 `.env`、API Key、私人数据库、人工审核 CSV、证据 JSONL、原始资料和运行日志；
- 文档只写真实完成并验证过的能力；
- 每项交付都要包含原理、改动文件、测试结果、已知风险和面试讲法。

## 直接发给笔记本 Codex 的后续优化提示词

---

## 本次执行记录（2026-09-07）

本次已按 P1 → P2 → P3 → P4 的验收边界完成代码、测试和可重复脚本收口。这里区分“代码与离线验证完成”和“需要外部环境或人工参与才能完成”，不把自动标签、静态配置检查或历史运行记录冒充人工/运行时验收。

### P1 人工审核

- 状态：`BLOCKED / 等待人工审核`。
- 已完成：保留 60 条私有审核 CSV 和 evidence JSONL 的工作流；增加 `scripts/summarize_human_review.py`，只输出聚合指标；`scripts/validate_human_review.py` 在未填写审核字段时拒绝冻结 Gold Set。
- 当前事实（2026-09-07）：第 1 至 4 批 `point_01` 至 `point_20` 已完成并通过批次级格式校验，20/60 条状态为 `approved`；剩余 40 条将按第 5 至 8 批、每批 10 条处理（趋势、排名、RAG、图表），仍是 `auto_draft_requires_human_review`，尚未生成 `dataset_human_reviewed_v1.json`。因此 P1 仍未完成，不能由 Agent 代填剩余人工结论。
- 验收动作：人工填完全部字段后运行：

```powershell
.\.venv\Scripts\python.exe scripts\validate_human_review.py
.\.venv\Scripts\python.exe scripts\summarize_human_review.py
```

### P2 SQLite/MySQL

- 状态：`代码完成；离线故障演练通过；真实 MySQL 本次未执行`。
- 已完成：`FINANCE_BACKEND=sqlite/mysql` 切换；MySQL 有界连接池、连接/读取超时和池等待超时；按配置执行 SQLite fallback；fallback 原因写入 API health、response execution context 和关键 trace 字段。
- 证据：`scripts/validate_backends.py` 输出到 `data/processed/mvp_dataset/backend_validation.json`。本次 SQLite 查询成功，注入式 MySQL 故障降级成功，3 条结果签名一致。
- 限制：Docker Desktop Linux engine 当前不可连接，因此没有在本次复核中验证真实 MySQL 连接、双后端在线结果一致性或 Compose 运行时健康状态。恢复 Docker 后需要执行 `docker compose up -d --build`、`docker compose ps`、`/health` 和一条 MySQL 查询。

### P3 评委交互展示台

- 状态：`已完成；本地 TestClient 回归通过`。
- 已完成：输入问题、固定示例、阶段状态、结构化意图、工具轨迹、事实/计算/引用职责分层、图表和引用、错误/无数据/降级展示；增加“本次执行环境”，展示 requested/effective backend、LLM 状态、fallback、步骤数和递归上限。
- 证据：`tests/integration/test_agent_and_api.py` 覆盖工作台、`/health`、`/v1/query`、图表静态资源、会话、异步任务和固定评测入口；本次测试套件共 `32 passed`。
- 演示边界：页面可以在无外部 LLM 时使用确定性 fallback 演示；LLM、MySQL、Redis 的真实性能和运行状态仍取决于部署环境。

### P4 RAG 对比实验

- 状态：`实验框架完成；语义 Embedding 与 Reranker 未执行`。
- 已执行：统一脚本 `scripts/benchmark_rag.py`，固定 5 条查询、`top_k=4`，记录索引数据库大小、实验耗时、每种方法查询延迟、代理命中率和 MRR 代理值；执行 FTS5、hashing vector、FTS5 + hashing hybrid。
- 本次结果摘要：FTS5 代理命中率 `0.4`，hashing vector `1.0`，hybrid `1.0`；平均延迟约为 `1.5 ms`、`6.8 ms`、`8.3 ms`。这些是词项重叠代理指标，不是人工标注 Recall@K/MRR。
- 未执行项：语义 Embedding 和 Hybrid + Reranker 因 provider 未配置，脚本明确记录 `NOT_EXECUTED`。当前 `char-ngram-hashing-v1` 只是可复现基线，不能称为语义 Embedding。
- 证据：`data/evaluation/rag_benchmark.json` 为本机运行产物，目录已被 `.gitignore` 排除。后续取得人工 Gold Set 和模型配置后，应在同一数据集、切片、过滤规则和 `top_k` 下重跑。

### 交付与面试口径

- 全量回归：`32 passed`；`compileall` 通过；`git diff --check` 通过；`docker compose config --quiet` 通过。
- 本次仍有一项真实环境阻塞：Docker Desktop engine 不可用。不能把 Compose 静态配置通过描述成 Docker 运行成功。
- 可以准确表述为：项目具备可追踪、可降级、可评测的财务分析 Agent 工程链路；SQLite 与注入式 MySQL 故障降级已验证，P1 人工 Gold Set、真实 Docker/MySQL 复验、语义 Embedding/Reranker 仍是明确边界。

## 图表技术核对记录（2026-09-08）

本节是对 P1 人工审核中图表部分的独立技术核对，不替代人工审核字段。

- 审计脚本：`scripts/audit_chart_artifacts.py`；结果：`data/evaluation/chart_audit.json`（本地运行产物，不提交）。
- 核对范围：`chart_01` 至 `chart_10`，共 10 条；不输出问题、答案、引用正文、审核人、备注或原始 Trace。
- 结构化结果：10/10 为 `success`；图表数均为 1；公司代码和指标编码与评测期望匹配；工具链均为 `financial_query → financial_analysis → chart_generation`。
- 图像结果：10/10 PNG 可解析、非空，统一尺寸 `980×560`；年份契约均为 2022、2023、2024；指标预期单位与项目指标定义一致。
- 可展示性：已目视检查 10 张图，均有折线和数据点，未发现空白、明显裁切、标题/坐标轴/图例严重重叠或标签溢出。
- 低风险提示：`chart_08` 的非白色内容触及画布右边缘附近，目视未见截断；保留为人工确认提示，不判定为失败。
- 当前判断：图表技术核对 `10/10 PASS`。因此人工审核表中的 `chart_correct`：趋势题应为 `NA`；`chart_01` 至 `chart_10` 请由审核人确认填写 `1`。当前 CSV 中出现的 `5` 不符合校验器允许值，不能冻结 Gold Set。

重新校正审核表后运行：

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
.\.venv\Scripts\python.exe scripts\validate_human_review.py
.\.venv\Scripts\python.exe scripts\summarize_human_review.py
```
- 私有审核文件、SQLite 数据库、原始资料、日志和迁移包均不应进入 GitHub；迁移包目录已加入 `.gitignore`。

将项目和私人评测文件导入完成、测试通过、展示台可打开后，把下面整段发给笔记本 Codex：

```text
这是 FinanceInsight Agent 项目，后续只在这台个人笔记本上开发。

请先读取 README.md、CONTEXT.md、docs/ARCHITECTURE.md、docs/EVALUATION.md、docs/HUMAN_EVALUATION_GUIDE.md、docs/DEPLOYMENT.md，以及 docs/笔记本接管与继续优化操作步骤.md 中“第六步”的四项优化路线。

先不要修改代码，请先完成接管审计：
1. 运行测试并记录当前基线。
2. 检查以下私人评测文件是否存在，但不要输出其中的完整私人内容，也不要提交到 GitHub：
   - evals/human_review_round1.csv
   - evals/human_review_round1.evidence.jsonl
3. 核实现有 SQLite/MySQL 切换和展示台能力，明确哪些已经完成，禁止重复实现。
4. 按固定顺序推进：
   P1 人工审核 60 条并冻结 Gold Set；
   P2 验收和补强 SQLite/MySQL 双后端；
   P3 优化面向评委的交互展示台；
   P4 完成五种 RAG 方案的对比实验。
5. 现在只制定 P1 的可执行计划，不要同时实施 P2—P4。
6. 把 60 条评测拆成便于我人工确认的小批次。你可以预分析和标记疑点，但不能代替我做最终人工结论。
7. 告诉我第一批需要审核哪些行、应该对照证据文件中的哪些字段、我需要填写什么。
8. 后续需要改代码时，先创建 codex/ 开头的分支，先补测试，改完运行回归。
9. 不读取、显示、复制或提交 .env 和任何 API Key；不提交 SQLite、人工审核 CSV、证据 JSONL、原始资料和日志。
10. 每个阶段结束后，用通俗中文输出：完成内容、证据、测试结果、失败案例、下一步和面试讲法。
```

---
