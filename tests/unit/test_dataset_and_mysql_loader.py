import importlib.util
from pathlib import Path

from finance_insight.ingestion import load_mysql
from finance_insight.ingestion.sync_mysql import read_snapshot
from scripts.generate_eval_dataset import generate


def _initialize_demo_data(data_dir: Path) -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "init_demo_data.py"
    spec = importlib.util.spec_from_file_location("init_demo_data_for_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.initialize_demo_data(data_dir)


def test_mysql_loader_is_importable_as_package_module():
    assert callable(load_mysql.read_rows)
    assert callable(load_mysql.load_rows)


def test_extended_evaluation_draft_has_60_unique_cases(tmp_path):
    _initialize_demo_data(tmp_path)
    cases = generate(tmp_path / "finance_insight.sqlite3")
    assert len(cases) == 60
    assert len({case["id"] for case in cases}) == 60
    assert {case["label_status"] for case in cases} == {"auto_draft_requires_human_review"}


def test_mysql_sync_snapshot_reads_all_portable_demo_rows(tmp_path):
    _initialize_demo_data(tmp_path)

    snapshot = read_snapshot(tmp_path / "finance_insight.sqlite3")
    assert len(snapshot["companies"]) == 10
    assert len(snapshot["periods"]) == 3
    assert len(snapshot["metrics"]) == 10
    assert len(snapshot["facts"]) == 300
    assert {row["quality_status"] for row in snapshot["facts"]} == {"synthetic_demo_only"}
