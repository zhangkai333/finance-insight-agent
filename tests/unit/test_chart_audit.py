import importlib.util
import json
from pathlib import Path

from PIL import Image


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "audit_chart_artifacts.py"
    spec = importlib.util.spec_from_file_location("chart_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_rejects_chart_path_with_wrong_metric(tmp_path):
    module = _load_module()
    artifact = tmp_path / "artifacts"
    artifact.mkdir()
    png = artifact / "trace_002821_roe.png"
    Image.new("RGB", (20, 20), "white").save(png)
    case = {"id": "chart_01", "expected_company": "002821", "expected_metrics": ["revenue"], "min_charts": 1}
    evidence = {
        "response": {
            "status": "success",
            "charts": [str(png)],
            "intent": {"period": {"years": [2022, 2023, 2024]}},
            "tool_events": [{"tool_name": name} for name in module.EXPECTED_TOOLS],
        }
    }
    result = module.audit_case(case, evidence, artifact)
    assert result["status"] == "FAIL"
    assert "expected_company_or_metric_not_in_chart_path" in result["findings"]


def test_audit_result_does_not_include_private_text(tmp_path):
    module = _load_module()
    dataset = tmp_path / "dataset.json"
    evidence = tmp_path / "evidence.jsonl"
    artifact = tmp_path / "artifacts"
    artifact.mkdir()
    png = artifact / "trace_002821_roe.png"
    Image.new("RGB", (20, 20), "black").save(png)
    dataset.write_text(json.dumps([{
        "id": "chart_01", "expected_company": "002821", "expected_metrics": ["roe"],
        "min_charts": 1, "question": "private question",
    }]), encoding="utf-8")
    evidence.write_text(json.dumps({
        "id": "chart_01", "question": "private question", "response": {
            "status": "success", "answer": "private answer", "charts": [str(png)],
            "intent": {"period": {"years": [2022, 2023, 2024]}},
            "tool_events": [{"tool_name": name} for name in module.EXPECTED_TOOLS],
        }
    }) + "\n", encoding="utf-8")
    result = module.audit(dataset, evidence, artifact)
    serialized = json.dumps(result, ensure_ascii=False)
    assert "private question" not in serialized
    assert "private answer" not in serialized
    assert result["passed"] == 1
