# 人工审核：第 1 批（5 条）

审核文件：`evals/human_review_round1.csv`。本批只填写以下 5 行，不修改其他行：

```text
point_01
point_02
point_03
point_04
point_05
```

每行按以下顺序检查并填入 CSV 末尾 12 个审核字段：

1. 对照 `question`、`expected_company`、`expected_metrics`、`expected_tools` 和 `actual_intent`，填写 `intent_correct`、`tool_correct`。
2. 对照 `expected_numeric`、`actual_answer` 与 `actual_status`，填写 `numeric_correct`。本批都属于直接数值查询，不需要年报引用或图表，因此 `citation_relevant_1_to_5`、`citation_supports_claim`、`chart_correct` 应填写 `NA`。
3. 检查回答是否只陈述已查询数值、单位、来源限制，填写 `answer_faithfulness_1_to_5`、`answer_completeness_1_to_5`、`question_naturalness_1_to_5`。
4. 填写 `review_status`：`approved`、`needs_revision` 或 `rejected`；填写审核人代号和可复现的 `review_notes`。

不要根据自动列 `auto_*` 直接判定正确。数据仍处于 `candidate_pending_review` 时，回答是否如实表达该边界，是忠实度审核的一部分。

审核完成本批后，把 5 行的审核字段结果发给我，或直接告诉我“第 1 批已填完”；我会只做格式校验、汇总 BadCase，并给出下一批，不会代替人工结论。
