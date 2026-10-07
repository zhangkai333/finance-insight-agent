# 人工评测操作指南

## 1. 这次人工评测在评什么

`evals/dataset_extended_draft.json` 的 60 条问题是自动生成初稿。程序回归 60/60 只说明“代码与自动标签一致”，不能证明标签本身正确，也不能证明答案忠实、引用充分或问题自然。因此人工评测要同时审核：

1. **题目与标签**：公司、年份、指标、期望工具是否标对；
2. **结构化结果**：意图、工具调用、数值和排序是否正确；
3. **生成结果**：回答是否只基于证据，是否完整；
4. **RAG 证据**：引用是否相关，是否真的支持回答中的原因判断；
5. **图表**：指标、公司、年份、单位和曲线是否正确。

## 2. 生成审核表

只用已有自动评测报告生成空白审核表（不会调用 DeepSeek）：

```powershell
$env:PYTHONPATH = Join-Path $PWD "src"
python scripts/export_human_review.py
```

若要把每道题当前的完整答案、引用和图表一起导出：

```powershell
# 确认 .env/进程环境中已配置 DeepSeek Key 后运行
python scripts/export_human_review.py --run-agent --use-llm
```

输出：

- `evals/human_review_round1.csv`：Excel/WPS 可直接打开；文件采用 UTF-8 BOM；
- `evals/human_review_round1.evidence.jsonl`：仅在 `--run-agent` 时生成，保留完整原始响应，便于追溯。

建议先复制一份 CSV 再标注，避免重新导出覆盖人工结果。首轮可按类别分批处理：20 条 point query、10 条 trend、10 条 ranking、10 条 RAG、10 条 chart。`actual_charts` 使用项目相对路径，可从仓库根目录定位 PNG。

## 3. 字段填写规则

| 字段 | 填写规则 |
|---|---|
| `intent_correct` | `1` 正确，`0` 错误；核对公司、年份、指标和任务类型 |
| `tool_correct` | `1` 正确，`0` 错误；允许的工具顺序以题目实际需求为准，不要机械服从自动标签 |
| `numeric_correct` | `1` 正确，`0` 错误，`NA` 不涉及数值；需对照 SQLite/MySQL 或年报原表 |
| `citation_relevant_1_to_5` | 1 完全无关；3 部分相关；5 高度相关；无引用要求填 `NA` |
| `citation_supports_claim` | 引用能直接支持回答中的原因/事实填 `1`，否则 `0`；不涉及填 `NA` |
| `chart_correct` | 公司、指标、年份、值、单位均正确填 `1`；否则 `0`；无图填 `NA` |
| `answer_faithfulness_1_to_5` | 1 大量臆测；3 有少量超出证据；5 所有关键陈述均有事实或引用支持 |
| `answer_completeness_1_to_5` | 1 基本未答；3 回答主要问题但有缺项；5 完整覆盖题目 |
| `question_naturalness_1_to_5` | 1 不可用；3 能理解但生硬；5 像真实用户问题 |
| `review_status` | `approved`、`needs_revision` 或 `rejected` |
| `reviewer` | 审核人姓名/代号 |
| `review_notes` | 写明错误位置、正确答案及证据页码；不要只写“有问题” |

## 4. 每条问题的实际审核顺序

1. 阅读 `question`，先在不看自动标签的情况下判断正确公司、期间、指标和工具；
2. 对照 `expected_*`，判断标签是否需要修订；
3. 查看 `actual_intent` 与 `actual_tools`；
4. 对问数/趋势/排名题，直接查询事实库并核对值、单位、同比公式和排序；
5. 对 RAG 题，打开引用对应的年报页，判断“相关”与“支持结论”两件不同的事；
6. 对图表题，打开 `actual_charts` 指向的 PNG，检查标题、轴、单位、年份和值；
7. 阅读最终答案，检查是否有无来源的因果解释、投资建议或数字抄错；
8. 填完评分、状态和具体备注。

## 5. 抽检与冻结 Gold Set

- 第一轮由主审核人完成 60 条；
- 至少随机抽 12 条（20%），其中 RAG 题不少于 4 条，由第二人独立复核；
- 二人不一致时讨论并保留修改说明；
- 修正问题或标签后，不要静默覆盖：复制为 `evals/dataset_human_reviewed_v1.json`；
- 将 `label_status` 改为 `human_reviewed_v1`，记录审核日期和审核人；
- 再运行程序评测，报告命名为 `data/evaluation/report_human_reviewed_v1.json`。

最终至少报告：人工批准率、各类别批准率、数值正确率、引用支持率、忠实度均值、完整度均值，以及双人抽检一致率。60 条全由同一人审核时，不要声称是“双人标注”。

## 6. 常见误判

- “返回了引用”不等于“引用支持结论”；
- 数值正确但单位错误，`numeric_correct` 应判错；
- 自动工具序列与自动标签一致，但题目本身不需要该工具，标签仍应修订；
- 图生成成功但画错指标/单位，`chart_correct` 应判错；
- 年报只陈述现象，回答却把它写成确定因果关系，忠实度要降分。

