# 人工审核：第 3 批（5 条）

审核文件：`evals/human_review_round1.csv`。本批只填写以下 5 行，不修改其他行：

```text
point_11
point_12
point_13
point_14
point_15
```

本批 5 条均为 `point_query`，期望工具均为 `financial_query`，不要求年报引用或图表。因此每行的 `citation_relevant_1_to_5`、`citation_supports_claim`、`chart_correct` 应填写 `NA`。

审核时重点核对：

1. 公司、年份、指标和任务类型是否正确；
2. `actual_intent` 是否解析出正确的公司、期间和指标；
3. `actual_tools` 是否使用了 `financial_query`，没有无必要的额外工具；
4. `actual_answer` 的数值、单位和数据边界是否与事实库及 `expected_numeric` 一致；
5. 回答是否完整、忠实，没有添加证据之外的因果判断或投资建议。

每行按 CSV 末尾的 12 个字段填写：

```text
intent_correct,tool_correct,numeric_correct,
citation_relevant_1_to_5,citation_supports_claim,chart_correct,
answer_faithfulness_1_to_5,answer_completeness_1_to_5,
question_naturalness_1_to_5,review_status,reviewer,review_notes
```

允许值：布尔字段填 `0`、`1` 或 `NA`；评分填 `1` 至 `5` 或 `NA`；状态填 `approved`、`needs_revision` 或 `rejected`。审核备注应写明错误位置、正确值或边界判断依据，不要只写“有问题”。

不要根据 `auto_*` 字段直接判定；它们只表示自动评测结果，最终结论由人工审核填写。

完成后告诉我“第 3 批已填完”。我会只做格式校验和隐私安全汇总，不代替人工结论。
