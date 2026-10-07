import pytest

from finance_insight.ingestion.pdf_pipeline import _normalise_output


def _payload(unit: str) -> dict:
    return {
        "document": {
            "stock_code": "002821",
            "company_name": "凯莱英",
            "report_year": 2024,
            "document_type": "annual_report",
        },
        "facts": [
            {
                "report_year": 2024,
                "metric_code": "revenue",
                "metric_value": 500000,
                "normalized_unit": unit,
                "source_page": 10,
            }
        ],
    }


def test_pdf_output_accepts_catalog_unit():
    result = _normalise_output(_payload("万元"), "annual.pdf", pages=20)

    assert result["facts"][0]["normalized_unit"] == "万元"


def test_pdf_output_rejects_wrong_normalized_unit():
    with pytest.raises(ValueError, match="normalized_unit 应为 万元"):
        _normalise_output(_payload("元"), "annual.pdf", pages=20)
