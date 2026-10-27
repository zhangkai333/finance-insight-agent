# Data Dictionary

## 1. 数据范围

| 项目 | 当前 MVP 范围 |
|---|---|
| 公司 | 10 家医药相关上市公司 |
| 结构化期间 | FY 2022、FY 2023、FY 2024 |
| 结构化事实 | 300 条 |
| 年报材料 | 10 份完全合成的 2024 经营说明 |
| 年报切片 | 20 条 |
| 文档检索数据库 | `.demo-data/rag.sqlite3` |
| 财务事实数据库 | `.demo-data/finance_insight.sqlite3` |

公开 Demo 中所有数值和经营说明均为虚构测试内容，质量标记为
`synthetic_demo_only`，不代表任何上市公司的真实披露。

## 2. 结构化事实实体

### `companies`

公司主数据，业务主键为 `stock_code`。

### `report_periods`

报告期间维度。MVP 查询固定使用 `period_code='FY'`。

### `metric_definitions`

| metric_code | 含义 | 单位 | 类型 |
|---|---|---|---|
| `revenue` | 营业收入 | 万元 | reported |
| `net_profit_attributable` | 归母净利润 | 万元 | reported |
| `net_profit_excl_non_recurring` | 扣非归母净利润 | 万元 | reported |
| `operating_cash_flow` | 经营活动现金流量净额 | 万元 | reported |
| `eps` | 基本每股收益 | 元/股 | reported |
| `roe` | 加权平均净资产收益率 | % | reported |
| `total_assets` | 总资产 | 万元 | reported |
| `net_assets` | 归母净资产 | 万元 | reported |
| `net_margin` | 净利率 | % | derived |
| `operating_cash_margin` | 经营现金流/营业收入 | % | derived |

### `financial_facts`

事实表，唯一业务键：`(company_id, report_period_id, metric_id)`。

重要字段：

| 字段 | 作用 |
|---|---|
| `metric_value` | 归一化数值 |
| `normalized_unit` | 统一后的单位 |
| `raw_value` / `raw_unit` | 溯源用原始值和原始单位 |
| `source_file` / `source_page` | 可追溯来源 |
| `quality_status` | 数据质量状态 |
| `extraction_method` | 采集/抽取方法 |

### 数据治理与可追溯性

- `ingestion_batches`：记录导入批次、源路径、hash、行数和状态；
- `raw_financial_rows`：保留原始行 payload；
- `data_quality_issues`：记录质量问题；
- `v_annual_financial_summary`：年度宽表查询视图。

## 3. 文档与 RAG 实体

### `documents`

保存公司、报告年、文档类型、源文件、页数和解析器。唯一键：`(stock_code, document_type, report_year, source_file)`。

### `document_chunks`

按页和 chunk 序号保存文本。唯一键：`(document_id, page_number, chunk_index)`。引用必须携带 `source_file` 和 `page_number`。

### `document_chunks_fts`

SQLite FTS5 虚拟表，使用 `trigram` tokenizer 完成词法检索。

### `chunk_vectors`

sqlite-vec 虚拟表：

```text
chunk_id INTEGER PRIMARY KEY
embedding float[256]
```

当前向量是 `char-ngram-hashing-v1`。可在不改变 Tool 输入输出契约的情况下替换成 BGE、OpenAI-compatible embedding 或其他 embedding provider。

## 4. 数据质量边界

- 本项目不向用户提供投资建议；
- 当前仅包含已入库范围，超出时间或公司范围时工具返回可解释错误；
- RAG 的“原因”是合成材料文本片段，不等同于真实年报或审计结论；
- derived 指标可通过 `formula` 字段解释，但正式计算在 Python 工具中完成并保留原始事实。
