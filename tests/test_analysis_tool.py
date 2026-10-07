from finance_insight.tools.analysis_tool import FinancialAnalysisTool


def _row(year: int, value: float) -> dict:
    return {
        "stock_code": "002821",
        "company_name": "凯莱英",
        "report_year": year,
        "metric_code": "revenue",
        "metric_name": "营业收入",
        "metric_value": value,
        "normalized_unit": "万元",
    }


def test_sparse_years_use_elapsed_years_for_cagr_and_skip_yoy():
    result = FinancialAnalysisTool().run([_row(2022, 100), _row(2024, 144)])

    series = result.data["series"][0]
    assert series["cagr_pct"] == 20.0
    assert "yoy_pct" not in series["points"][0]
    assert series["points"][1]["yoy_pct"] is None
    assert result.data["anomalies"] == []


def test_consecutive_years_still_calculate_yoy_and_anomalies():
    result = FinancialAnalysisTool().run([_row(2022, 100), _row(2023, 130)])

    series = result.data["series"][0]
    assert series["cagr_pct"] == 30.0
    assert series["points"][1]["yoy_pct"] == 30.0
    assert result.data["anomalies"][0]["year"] == 2023
