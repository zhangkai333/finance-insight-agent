# FinanceInsight Agent 项目需求说明

> 项目名称：FinanceInsight Agent —— 上市公司财报智能分析 Agent  
> 文档状态：Phase 0 需求与业务分析定稿（第一版）  
> 更新日期：2026-08-26

## 1. 项目背景

项目以 2026 年泰迪杯 B 题“上市公司财报智能问数”场景为业务背景，结合项目开发者已有的泰迪杯 C 题数据分析经验和 Dify + RAG 金融知识库经验，使用 Python 从 0 构建一个面向求职的企业级金融 AI 应用。

项目重点不是模型训练，而是展示如何把大模型接入真实业务，并形成可查询、可计算、可检索、可解释、可评测、可部署的 Agent 系统。

## 2. 目标用户与核心问题

### 目标用户

企业财务分析人员。

### 用户痛点

用户需要在多年度上市公司财报中查找财务指标、进行跨年度比较、计算衍生指标、识别异常变化，并回到年报或研报中寻找经营原因。人工在 PDF、表格和分析工具之间切换，过程耗时，且容易出现指标口径、单位、年度对应和引用缺失问题。

### 核心价值

FinanceInsight Agent 将以下流程串成闭环：

```text
自然语言问题
→ 识别公司、期间、指标和任务意图
→ 查询结构化财务事实
→ Python 计算和异常分析
→ 检索年报/研报原文依据
→ 生成图表
→ 输出带来源的分析结果或报告
```

## 3. 第一版业务范围

采用“先单一、后复合”的路线，不一开始实现全能 Agent。

### MVP 必须支持

1. 单公司单指标查询；
2. 单公司多年度指标查询；
3. 同比增长率、利润率、平均值等指标计算；
4. 财报和研报原文检索；
5. 异常年份或异常指标识别；
6. 趋势图和对比图生成；
7. 综合财务分析报告。

### 第一轮数据范围

先冻结一个可控、可验证的跨公司 MVP 数据集：

```text
公司：B 题目标公司 10 家
年份：FY 2022—FY 2024
财报：每家公司 1 份 2024 年非摘要年度报告
研报：本阶段暂不批量读取，Phase 3 按 RAG 验收需要再加入
```

当前数据清单和完备性结论见：

```text
docs/DATA_READINESS.md
data/processed/mvp_dataset/mvp_financial_extraction_audit.json
data/processed/mvp_dataset/mvp_financial_validation.json
```

Python 程序只读取选定的 10 份年报，不扫描全部 180 份财报和全部研报。若后续需要 2025Q3，再通过 `--include-q3` 显式扩展，不改变当前 MVP 的年度数据边界。

### 第一条可验收链路

```text
“查询凯莱英 2022—2024 年营业收入、净利润和 ROE”
→ 结构化查询
→ 返回年度数据、单位和来源
```

后续逐步加入：

```text
同比计算
→ 异常识别
→ 年报原因检索
→ 图表生成
→ 综合报告
→ LangGraph 多步骤 Agent
```

## 4. 问题类型与能力分工

| 问题类型 | 主要模块 |
|---|---|
| 精确数值查询 | SQL Tool |
| 多年度/多公司筛选 | SQL Tool |
| 同比、利润率、均值、CAGR | Python Analysis Tool |
| 异常年份识别 | Python Analysis Tool |
| 财务概念和指标口径解释 | RAG Tool |
| 年报对经营变化的解释 | RAG Tool |
| 趋势图和对比图 | Chart Tool |
| 复杂任务拆解与结果汇总 | Agent / LangGraph |

核心原则：

> LLM 负责理解、规划和汇总；SQL 负责查事实；Python 负责精确计算；RAG 负责找原文依据；Chart Tool 负责可视化。

## 5. Agent 与 Tool 设计

第一版使用职责单一的工具：

```text
financial_query_tool
financial_calculation_tool
annual_report_search_tool
anomaly_detection_tool
chart_generation_tool
```

报告生成先作为 Agent 的最终汇总节点，不急于设计成独立 Tool。

路由分三阶段演进：

1. 显式路由：用规则理解工具边界；
2. Structured Output 路由：让 LLM 输出意图、参数和所需工具；
3. LangGraph 动态编排：依据 State 决定下一步、继续执行、重试或结束。

不使用一个包办所有事情的超级工具。

## 6. 数据库最终设计

采用“原始层 + 统一语义层 + 查询视图层 + 文档层”的混合设计。

### 原始层

保留官方 B 题结构，作为不可覆盖的输入依据：

```text
raw_company_info
raw_core_performance
raw_balance_sheet
raw_income_statement
raw_cash_flow
```

### 统一语义层

```text
companies
report_periods
metric_definitions
metric_aliases
financial_facts
```

核心关系：

```text
companies
  └── report_periods
        └── financial_facts
              └── metric_definitions
```

`financial_facts` 一行表示一个公司、一个报告期间、一个标准指标的事实值，并保留：

```text
metric_value
unit
accounting_scope
value_type
source_table
source_column
source_row_key
document_id
source_page
quality_status
extraction_method
```

### 查询视图层

建立面向 Agent 的高频查询视图，例如：

```text
v_annual_financial_summary
```

该视图将收入、净利润、ROE 等常用指标展开，降低 LLM 生成 SQL 的复杂度。

### 文档层

```text
documents
document_chunks
```

文档元数据保存在 MySQL，文本向量后续放入独立向量数据库。每个检索片段必须关联公司、年份、文档、页码和章节。

第一版结构化事实覆盖 8 个原始指标和 2 个 Python 衍生指标，具体清单见 `docs/DATA_READINESS.md`。Agent 首先围绕营业收入、归母净利润、ROE、经营现金流等核心指标实现，其他科目按问题集和验收结果增量加入。

官方已经提供的指标可作为已报告事实；用户临时要求的同比、利润率、平均值等由 Python 动态计算，不让 LLM 直接计算。

## 7. 技术路线

目标技术栈：

```text
Python
OpenAI-compatible LLM API
Pandas
SQL / MySQL
Embedding
Vector Database
Function Calling / Tool Calling
LangGraph
FastAPI
Redis
异步任务
Docker / Docker Compose
MCP
Agent Evaluation
Logging / Trace / Retry / Fallback
Git / GitHub
```

技术加入条件：

> 每项技术必须在项目中有真实用途，不为堆叠简历关键词而加入。

## 8. 开发阶段

严格按以下顺序推进，每阶段先解释目标、实现一个最小切片、运行验证，再进入下一阶段：

```text
Phase 0 需求与业务分析
Phase 1 B题数据理解与数据建模
Phase 2 财报数据入库
Phase 3 RAG知识库
Phase 4 Python调用LLM API
Phase 5 Structured Output
Phase 6 Function Calling / Tool Calling
Phase 7 SQL Tool
Phase 8 RAG Tool
Phase 9 Python Analysis Tool
Phase 10 Chart Tool
Phase 11 LangGraph Agent
Phase 12 State / Context / Memory
Phase 13 多步骤任务执行
Phase 14 Retry / Fallback / 异常处理
Phase 15 FastAPI
Phase 16 Redis / 缓存 / 会话
Phase 17 Docker部署
Phase 18 MCP
Phase 19 Agent Evaluation
Phase 20 Logging / Trace / Observability
Phase 21 测试
Phase 22 项目文档
Phase 23 简历包装
Phase 24 模拟面试
```

## 9. 学习与协作方式

1. 不直接一次性生成整个项目；
2. 每完成一个阶段，解释该阶段解决的业务和工程问题；
3. 说明对应的岗位 JD 能力；
4. 关键技术决策先说明方案、优缺点和推荐理由；
5. 每个模块先实现最小可运行版本；
6. 每一步必须实际运行验证；
7. 发现问题时先建立最小复现，再修复；
8. 每完成一个模块，补充面试官可能的追问；
9. 每完成一个模块，提供一道理解检查题；
10. 不跨阶段堆叠功能，不在未验证时进入下一阶段。

## 10. 非目标

本项目不以以下内容为主线：

```text
模型训练
Transformer 数学推导
LoRA 微调
RLHF
CUDA
分布式训练
深度学习算法研究
```

可以解释相关概念，但不将其作为主要实现内容。

## 11. 交付标准

最终项目应能够演示：

```text
用户输入复杂财报问题
→ Agent 识别任务
→ 查询 MySQL
→ 调用 Python 计算
→ 检索年报/研报
→ 生成图表
→ 输出有来源的分析报告
→ 记录工具调用轨迹
→ 支持评测、重试和错误降级
→ 通过 FastAPI 提供服务
→ 使用 Docker 部署
```

同时，开发者能够向面试官解释：

- 为什么这样设计 Agent；
- LLM 在系统中的职责和边界；
- Python 如何调用大模型；
- Structured Output 和 Tool Calling 如何工作；
- SQL 与 RAG 如何协同；
- LangGraph 为什么需要 State；
- FastAPI、Redis、Docker 和 MCP 在项目中的真实用途；
- 如何评测和优化 Agent。

## 12. 当前状态与下一步

Phase 0 的核心需求、业务边界、数据范围、工具分工和数据库方向已经确定。

下一步只做 Phase 1 的第一个最小切片：

```text
读取官方字段说明
→ 建立指标映射
→ 读取凯莱英三年样本的结构化数据
→ 输出数据质量与字段分析报告
```

暂不接入 LLM、RAG、Agent 或 Docker。
