# Phase 2.1 数据库模型设计

> 状态：设计完成，建表 SQL 已执行 SQLite 冒烟验证。  
> 日期：2026-08-26

## 1. 设计目标

数据库首先服务于 `financial_query_tool`，解决以下问题：

- 按公司、报告期间、指标查询精确财务事实；
- 支持 FY、Q1、半年报、Q3 等期间扩展；
- 新增指标时不需要修改事实表结构；
- 保存原始值、标准化值、单位、口径和来源；
- 为后续 Python Analysis Tool 和 Chart Tool 提供稳定输入；
- 为后续 RAG 文档层预留关联字段。

## 2. 采用的模型

本阶段采用：

```text
长表事实模型 + 关系维度表 + 高频查询视图
```

核心关系：

```text
companies 1 ─── N report_periods
companies 1 ─── N financial_facts N ─── 1 metric_definitions
report_periods 1 ─── N financial_facts
```

`financial_facts` 的业务唯一键为：

```text
(company_id, report_period_id, metric_id)
```

## 3. 表职责

### companies

保存公司主数据。股票代码是业务侧稳定标识，数据库内部使用 `company_id` 作为外键。

### report_periods

保存报告期间，而不是只保存年份。这样同一家公司未来可以同时拥有 FY 2024 和 2025Q3。

### metric_definitions

保存标准指标编码、中文名称、默认单位、指标分类和公式说明。LLM 和 Tool 只应使用 `metric_code`，不直接依赖 PDF 中可能变化的中文表头。

### financial_facts

保存一个公司、一个期间、一个标准指标对应的事实。金额和比率都进入同一张事实表，但通过 `normalized_unit` 区分单位，并保留 `value_type` 表示 reported 或 derived。

### v_annual_financial_summary

面向查询工具的年度宽视图。底层仍是长表，查询常用指标时不需要让 Agent 生成复杂的透视 SQL。

### ingestion_batches / raw_financial_rows

保存一次导入批次和 CSV 原始行 JSON。这样导入后的标准事实出现问题时，可以回到原始行重放，而不必重新扫描 PDF。

### data_quality_issues

保存导入或校验阶段发现的 warning/error。当前批次没有质量错误，但表结构已经预留。

## 4. 溯源与质量策略

当前 Phase 2 先保留 `source_file` 和 `source_page`，因为 Phase 1 还没有正式的 documents 主表。Phase 3 建立文档层后，再将文件抽象为 `document_id`。

每条事实都保留：

- `raw_value`、`raw_unit`；
- `metric_value`、`normalized_unit`；
- `accounting_scope`；
- `value_type`；
- `source_file`、`source_page`；
- `extraction_method`；
- `quality_status`。

## 5. 迁移策略

先用 SQLite 验证模型和查询逻辑，再迁移 MySQL。两者都使用关系表和唯一约束；迁移时主要调整自增主键、精确数值类型和时间字段，而不是重做业务模型。

已生成 MySQL 8 建表脚本：`db/schema.mysql.sql`，以及可配置连接参数的导入脚本：`src/finance_insight/ingestion/load_mysql.py`。当前开发环境没有安装 Docker、MySQL 客户端或 MySQL 服务，因此 MySQL 运行时回归会在具备数据库服务时执行，不能用 SQLite 冒充 MySQL 测试。

## 6. 当前不在本阶段实现的内容

- 原始层五张 B 题附件表；
- `documents`、`document_chunks` 和向量库；
- Docker Compose；
- 数据库迁移工具；
- 用户权限和多租户隔离。

这些已记录在根目录 `待补充文档.md`，后续按阶段补充并实测。
