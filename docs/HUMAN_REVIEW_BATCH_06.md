# 人工审核：第 6 批（10 条排名分析）

审核文件：`evals/human_review_round1.csv`。本批只填写以下 10 行，不修改其他行：

```text
ranking_01
ranking_02
ranking_03
ranking_04
ranking_05
ranking_06
ranking_07
ranking_08
ranking_09
ranking_10
```

本批均为 `ranking`，期望工具为 `financial_query`，不要求年报引用或图表。因此每行的 `citation_relevant_1_to_5`、`citation_supports_claim`、`chart_correct` 应填写 `NA`。

审核时重点核对：

1. 排名年份、指标、公司范围和排序方向是否正确；
2. `actual_intent` 是否解析出正确的任务类型、期间和指标；
3. `actual_tools` 是否使用了 `financial_query`，没有无必要的额外工具；
4. `actual_answer` 中每家公司、数值、单位和名次是否与事实库一致，降序/升序是否符合指标含义；
5. 回答是否覆盖题目要求的排名结果，并明确数据边界，不添加证据之外的投资判断。

每行按 CSV 末尾的 12 个字段填写。无引用、无图表的字段填 `NA`；其他布尔字段填 `0`、`1`，评分填 `1` 至 `5`，状态填 `approved`、`needs_revision` 或 `rejected`。审核备注应写明错误位置、正确值或排序依据，不要只写“有问题”。

不要根据 `auto_*` 字段直接判定；它们只表示自动评测结果，最终结论由人工审核填写。

完成后告诉我“第 6 批已填完”。我会只做格式校验和隐私安全汇总，不代替人工结论。
