# 人工审核：第 8 批（10 条图表分析）

审核文件：`evals/human_review_round1.csv`。本批只填写以下 10 行，不修改其他行：

```text
chart_01
chart_02
chart_03
chart_04
chart_05
chart_06
chart_07
chart_08
chart_09
chart_10
```

本批均为 `chart`，期望工具顺序为 `financial_query`、`financial_analysis`、`chart_generation`，每条至少需要 1 张图表，不要求年报引用。因此 `citation_relevant_1_to_5`、`citation_supports_claim` 应填写 `NA`；`chart_correct` 必须打开实际 PNG 后判断，不能仅依据图表文件存在判定正确。

审核时重点核对：

1. 公司、年份范围、指标和绘图任务类型是否正确；
2. `actual_intent` 与 `actual_tools` 是否完成事实查询、计算分析和图表生成；
3. 图表标题、横轴年份、纵轴指标、单位、公司和数据点是否与题目及事实库一致；
4. 图表曲线/柱形的方向、数值和数据范围是否正确，是否存在指标错位、单位错误或年份错位；
5. `actual_answer` 是否与图表和结构化结果一致，回答是否完整且没有超出证据的结论。

每行按 CSV 末尾的 12 个字段填写。无引用字段填 `NA`；`chart_correct` 填 `0` 或 `1`；其他布尔字段填 `0`、`1`，评分填 `1` 至 `5`，状态填 `approved`、`needs_revision` 或 `rejected`。审核备注应写明图表错误位置、正确指标/单位/年份或核对依据，不要只写“有问题”。

不要根据 `auto_*` 字段或“PNG 能打开”直接判定；最终结论由人工核对图表内容填写。

完成后告诉我“第 8 批已填完”。我会只做格式校验、聚合统计和 Gold Set 冻结前检查，不代替人工结论。
