# Phase 2.2 SQLite 数据入库报告

> 状态：完成并通过实测  
> 日期：2026-08-26

## 1. 本阶段目标

把 Phase 1 的 `mvp_financial_candidates.csv` 写入 Phase 2.1 设计的关系模型，验证数据库可以实际支撑查询，而不是只停留在建表层面。

## 2. 实现文件

- 导入脚本：`src/finance_insight/ingestion/load_sqlite.py`；
- 查询验证脚本：`src/finance_insight/ingestion/verify_phase2_queries.py`；
- 建表 SQL：`db/schema.sql`；
- SQLite 数据库：`data/finance_insight.sqlite3`。

## 3. 导入流程

```text
读取 CSV
→ upsert companies
→ upsert report_periods
→ upsert metric_definitions
→ upsert financial_facts
→ 事务提交
```

事实表使用 `(company_id, report_period_id, metric_id)` 唯一约束。重复执行导入不会追加重复事实，而是更新同一业务键的数据。

本阶段把当前财报口径统一暂存为 `consolidated`，因为 Phase 1 的候选数据来自年报主要会计数据摘要表；后续接入更细粒度报表时，需要将合并口径、母公司口径等拆分为可验证字段。

## 4. 导入结果

| 表/对象 | 数量 |
|---|---:|
| companies | 10 |
| report_periods | 3 |
| metric_definitions | 10 |
| financial_facts | 300 |
| v_annual_financial_summary 行数 | 30 |

## 5. SQL 验收查询

### 查询一：凯莱英 FY 2022—FY 2024 收入趋势

返回 3 行，金额单位为万元：

| 年份 | 营业收入 | 净利率 |
|---:|---:|---:|
| 2022 | 1,025,532.539282 | 32.194347% |
| 2023 | 782,519.029827 | 28.993678% |
| 2024 | 580,465.733692 | 16.348080% |

### 查询二：凯莱英 FY 2022—FY 2024 ROE 趋势

返回 3 行：

| 年份 | ROE |
|---:|---:|
| 2022 | 23.56% |
| 2023 | 13.66% |
| 2024 | 5.56% |

### 查询三：2024 年 10 家公司营业收入排名

返回 10 行，排序和行数校验通过。2024 年收入最高的样本公司股票代码为 `603259`，收入为 `3,924,143.135988` 万元。

## 6. 运行命令

```powershell
python src/finance_insight/ingestion/load_sqlite.py `
  --csv data/processed/mvp_dataset/mvp_financial_candidates.csv `
  --schema db/schema.sql `
  --db data/finance_insight.sqlite3

python src/finance_insight/ingestion/verify_phase2_queries.py `
  --db data/finance_insight.sqlite3 `
  --output data/processed/mvp_dataset/phase2_query_validation.json
```

## 7. MySQL 迁移准备

已生成：

- MySQL 8 建表脚本：`db/schema.mysql.sql`；
- MySQL 导入脚本：`src/finance_insight/ingestion/load_mysql.py`；
- MySQL 使用 `DECIMAL(24, 6)` 保存数值，SQLite 使用 `NUMERIC`；
- MySQL 使用 InnoDB 和外键约束；
- MySQL 使用 `%s` 参数占位符和 `ON DUPLICATE KEY UPDATE`。

当前开发环境检测结果：

```text
Docker：不可用
MySQL 客户端：不可用
MySQL 服务：未发现
```

因此 MySQL 真实连接回归尚未执行，不能把这部分标记为已实测。脚本参数、SQL 和迁移边界已经准备好，后续有 MySQL 服务时再执行同一组查询回归。

## 8. 当前边界

本阶段尚未加入：

- Docker Compose；
- B 题官方原始层五张细分表；
- documents/document_chunks；
- 数据库迁移工具；
- 完整权限和多租户；
- 2025Q3 数据。

这些内容已经登记到 `待补充文档.md`，后续必须按阶段实现并实测。
