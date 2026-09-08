# 人工审核：第 5 批（10 条趋势分析）

审核文件：`evals/human_review_round1.csv`。本批只填写以下 10 行，不修改其他行：

```text
trend_01
trend_02
trend_03
trend_04
trend_05
trend_06
trend_07
trend_08
trend_09
trend_10
```

本批均为 `trend_analysis`，期望工具顺序为 `financial_query`、`financial_analysis`，不要求年报引用或图表。因此每行的 `citation_relevant_1_to_5`、`citation_supports_claim`、`chart_correct` 应填写 `NA`。

审核时重点核对：

1. 公司、年份范围、指标和趋势分析任务类型是否正确；
2. `actual_intent` 是否解析出正确的公司、期间和指标；
3. `actual_tools` 是否完成事实查询和 Python 分析，没有无必要的额外工具；
4. `actual_answer` 中各年份数值、单位、同比方向、变化结论和异常判断是否与事实库及 `actual_intent` 一致；
5. 回答是否覆盖题目要求的完整年份范围，且没有把相关性或现象写成证据不足的确定因果关系。

每行按 CSV 末尾的 12 个字段填写。无引用、无图表的字段填 `NA`；其他布尔字段填 `0`、`1`，评分填 `1` 至 `5`，状态填 `approved`、`needs_revision` 或 `rejected`。审核备注应写明错误位置、正确值或计算依据，不要只写“有问题”。

不要根据 `auto_*` 字段直接判定；它们只表示自动评测结果，最终结论由人工审核填写。

完成后告诉我“第 5 批已填完”。我会只做格式校验和隐私安全汇总，不代替人工结论。
