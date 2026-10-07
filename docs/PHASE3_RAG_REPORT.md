# Phase 3：年报 RAG 知识库报告

> 状态：以下索引数量与检索测试为 2026-08-26 历史记录，本轮未重新统计；当前实现状态见第 6 节。  
> 日期：2026-08-26

## 1. 本阶段目标

将 10 份选定的 2024 年非摘要年度报告解析成可检索文档，并保证检索结果能回到公司、年份、文件和页码，为后续 `annual_report_search_tool` 提供输入。

## 2. 当前实现

```text
PDF
→ pypdf 逐页解析
→ 空白清洗
→ 800 字符切片，120 字符重叠
→ 保存 document / chunk 元数据
→ SQLite FTS5 trigram 检索
→ 返回原文片段和页码引用
```

实现文件：

- `db/rag_schema.sql`；
- `src/finance_insight/ingestion/build_rag_index.py`；
- `src/finance_insight/ingestion/search_rag.py`；
- `src/finance_insight/ingestion/verify_rag_index.py`。

索引数据库：

- `data/rag.sqlite3`。

## 3. 索引结果

| 项目 | 数量 |
|---|---:|
| 年报文档 | 10 |
| PDF 页数 | 2,385 |
| 文档切片 | 4,178 |
| FTS 索引行 | 4,178 |
| 解析错误 | 0 |

每个切片保存：

- `stock_code`；
- `company_name`；
- `report_year`；
- `document_type`；
- `source_file`；
- `page_number`；
- `chunk_id`；
- `content`。

## 4. 检索测试

验证文件：`data/processed/mvp_dataset/rag_validation.json`。

测试结果：

```text
PASS
```

已验证：

1. 对凯莱英 2024 年报告检索“主要原因”，命中 3 个片段；
2. 对凯莱英 2024 年报告检索“研发投入”，命中 3 个片段；
3. 跨公司检索“研发投入”，命中 10 个片段；
4. 公司和年份过滤生效；
5. 每条结果都带来源文件、页码和原文内容。

示例结果可以定位到凯莱英 2024 年年报第 13 页，其中包含大订单、新业务爬坡、研发投入等经营变化原因。这说明结构化数据发现异常后，后续可以用 RAG 回查解释性文本。

## 5. 为什么本阶段先用 FTS5

当前环境没有安装 Embedding 模型、向量数据库或 MySQL/Docker 服务。因此本阶段先使用 SQLite FTS5 建立一个零外部依赖、可重复验证的 lexical RAG baseline。

这样做不是把 FTS5 当成最终方案，而是先验证三个关键事实：

- 文档能否被解析；
- 切片能否关联公司、年份和页码；
- 查询能否返回可引用原文。

后续再把检索后端替换为 Embedding + Vector Database，并使用同一套文档和引用契约回归测试。

## 6. 当前实现与限制

- 默认 SQLite FTS5 检索和词法/元数据重排已实现并用于本机演示；
- 本地 hashing vector + sqlite-vec 混合检索已有代码，但本轮未验证 sqlite-vec 依赖；
- 可选 OpenAI-compatible/BGE-M3 embedding、Chroma 向量库、jieba BM25 融合已有代码，当前环境未实测这些依赖、Key 和召回效果；
- 真正的语义 reranker 与人工标注的 chunk 级检索质量评测仍未完成；
- PDF OCR fallback；
- 研报批量接入；
- 检索质量数据集和 Recall@K 评测；
- 文档章节自动识别；
- MySQL `documents` 表与当前 RAG SQLite 文档表合并。

4,178 chunks / 2,385 pages 是历史索引报告，不是本轮重建与复核结果。新增 PDF 的 Markdown/JSON 入库路径见 `docs/INTERVIEW_GUIDE.md`。

## 7. 对应岗位 JD 能力

本阶段对应：

- 文档解析和清洗；
- RAG 文档切片；
- metadata filter；
- 引用溯源；
- 检索后端抽象；
- PDF 解析失败的降级意识；
- 为后续 Embedding / Vector DB 保留替换空间。
