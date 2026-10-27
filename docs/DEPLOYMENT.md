# Deployment

## Public Local Demo

The public repository uses synthetic data and does not include private annual
reports or financial databases.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\start-demo.ps1
```

The script creates `.demo-data/finance_insight.sqlite3` and
`.demo-data/rag.sqlite3` on first use. Use `-RefreshData` only when replacing
the synthetic demo databases.

## Docker Compose

```powershell
docker compose up -d --build
docker compose ps
```

Services:

- `api`: FastAPI workbench and Agent, exposed at `http://127.0.0.1:8000`;
- `mysql`: MySQL 8.4, retained in the `mysql_data` volume;
- `redis`: Redis 7 with AOF persistence, retained in the `redis_data` volume;
- `finagent_data`: synthetic SQLite sources, RAG index, charts, logs and tasks.

Startup sequence:

1. the API entrypoint creates synthetic SQLite finance and RAG databases;
2. the finance database is synchronized into MySQL;
3. the API starts with `FINANCE_BACKEND=mysql` and `REDIS_URL` enabled;
4. `/health` reports the effective MySQL and Redis backends.

Validated result:

- image build completed;
- `api`, `mysql` and `redis` are healthy;
- MySQL contains 10 companies, 3 periods and 300 facts;
- Redis stores and returns session results;
- restricted SQL queries use MySQL;
- RAG still returns citation-bearing SQLite FTS5/vector results;
- MCP stdio returns both `financial_query` and `annual_report_search`;
- the API evaluation task completes 6 / 6.

MySQL and Redis are intentionally not published to host ports. The API reaches
them through the Compose network.

## Optional Chroma + BM25

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,production-rag]"
.\scripts\start-demo.ps1 -RagBackend chroma
```

Without `EMBEDDING_API_KEY`, Chroma uses the reproducible
`char-ngram-hashing-v1` embedding and stores the index in
`.demo-data/chroma`. With a configured OpenAI-compatible embedding endpoint,
the same path uses `BAAI/bge-m3` and records the provider in retrieval traces.

## Optional LLM Provider

Set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` to enable structured intent
parsing and report synthesis. If the provider is unavailable, the workflow
records the failure and falls back to deterministic parsing and report
generation.

## Production Checklist

Before a production deployment:

- replace all default secrets;
- add authentication, authorization, CORS, and rate limiting;
- use read-only database credentials and audit logging;
- validate data licensing and source provenance;
- move artifacts to object storage with retention rules;
- use a durable queue for async work;
- add centralized logs, traces, metrics, and alerts;
- run failure, concurrency, recovery, and cost tests.
