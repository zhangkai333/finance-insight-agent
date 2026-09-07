from fastapi.testclient import TestClient


def test_api_query_and_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "api.db"))
    from app import main

    main.settings.database_path = tmp_path / "api.db"
    main.database = main.Database(main.settings.database_path)
    main.ingestor = main.DocumentIngestor(main.database)
    main.agent = main.FinancialAgent(main.database, main.settings)
    with TestClient(main.app) as client:
        upload = client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "report.md",
                    "公司收入同比增长18%，主要来自数据服务。".encode(),
                    "text/markdown",
                )
            },
        )
        assert upload.status_code == 200
        document_id = upload.json()["id"]
        response = client.post(
            "/api/v1/query",
            json={"question": "收入增长多少？", "document_ids": [document_id]},
        )
        assert response.status_code == 200
        trace_id = response.json()["trace_id"]
        trace = client.get(f"/api/v1/traces/{trace_id}")
        assert trace.status_code == 200
        assert {event["step"] for event in trace.json()["events"]} >= {
            "classify_intent",
            "hybrid_retrieval",
            "compose_answer",
            "validate_output",
        }
