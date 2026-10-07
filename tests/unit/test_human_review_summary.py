import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "summarize_human_review.py"
    spec = importlib.util.spec_from_file_location("human_review_summary", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(**updates):
    values = {
        "id": "case_01", "category": "point_query",
        "intent_correct": "1", "tool_correct": "1", "numeric_correct": "1",
        "citation_relevant_1_to_5": "NA", "citation_supports_claim": "NA", "chart_correct": "NA",
        "answer_faithfulness_1_to_5": "5", "answer_completeness_1_to_5": "5",
        "question_naturalness_1_to_5": "5", "review_status": "approved",
        "reviewer": "reviewer-a", "review_notes": "numbers checked",
    }
    values.update(updates)
    return values


def test_review_summary_is_aggregate_only_and_requires_all_60_rows():
    module = _load_module()
    result = module.summarize([_row()])
    assert result["status"] == "INCOMPLETE"
    assert result["reviewed_rows"] == 1
    assert "case_01" not in str(result)
    assert "reviewer-a" not in str(result)
    assert "numbers checked" not in str(result)


def test_review_reader_accepts_gb18030_spreadsheet_export(tmp_path):
    path = tmp_path / "review.csv"
    path.write_bytes("id,review_notes\ncase_01,已审核\n".encode("gb18030"))
    validator_path = Path(__file__).resolve().parents[2] / "scripts" / "validate_human_review.py"
    spec = importlib.util.spec_from_file_location("review_validator", validator_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.read_review_rows(path) == [{"id": "case_01", "review_notes": "已审核"}]
