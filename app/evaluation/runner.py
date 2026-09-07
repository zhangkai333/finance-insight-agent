import asyncio
import json
import sys
import uuid
from pathlib import Path

from app.agent.graph import FinancialAgent
from app.config import get_settings
from app.models import QueryRequest
from app.rag.ingestion import DocumentIngestor
from app.storage import Database


async def evaluate(dataset_path: Path) -> dict:
    database = Database(get_settings().database_path)
    database.initialize()
    ingestor = DocumentIngestor(database)
    _ensure_sample_documents(ingestor)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    documents = {item.name: item for item in ingestor.list_documents()}
    agent = FinancialAgent(database, get_settings())
    results = []
    for item in dataset:
        document = documents.get(item["document"])
        state = await agent.run(
            QueryRequest(
                question=item["question"], document_ids=[document.id] if document else None
            )
        )
        cited = bool(state.get("citations")) or not item["must_cite"]
        passed = (
            state.get("intent") == item["expected_intent"] and cited and bool(state.get("answer"))
        )
        result = {
            "id": item["id"],
            "passed": passed,
            "expected_intent": item["expected_intent"],
            "actual_intent": state.get("intent"),
            "citation_count": len(state.get("citations", [])),
            "answer": state.get("answer", ""),
            "root_cause": None if passed else _root_cause(state, item),
        }
        results.append(result)
        if not passed:
            database.record_bad_case(
                f"bc_{uuid.uuid4().hex}",
                item["id"],
                item["question"],
                item["expected_intent"],
                state["intent"].value if state.get("intent") else None,
                state.get("answer", ""),
                result["root_cause"],
            )
    passed_count = sum(item["passed"] for item in results)
    return {
        "total": len(results),
        "passed": passed_count,
        "pass_rate": passed_count / max(1, len(results)),
        "cases": results,
    }


def _ensure_sample_documents(ingestor: DocumentIngestor) -> None:
    sample_dir = Path(__file__).resolve().parents[2] / "data" / "samples"
    for name in ("sample_annual_report.md", "sample_financials.csv"):
        path = sample_dir / name
        if path.exists():
            ingestor.ingest(name, path.read_bytes(), "text/csv" if path.suffix == ".csv" else "text/markdown")


def _root_cause(state: dict, item: dict) -> str:
    if state.get("intent") != item["expected_intent"]:
        return "prompt"
    if item["must_cite"] and not state.get("citations"):
        return "retrieval"
    return "code_bug"


def main() -> None:
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("app/evaluation/dataset.json")
    result = asyncio.run(evaluate(dataset))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
