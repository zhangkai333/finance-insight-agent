# Capability Matrix

This matrix separates capabilities that were executed from adapter-only
integrations that require external credentials or infrastructure.

| Capability | Public default | Verified in this workspace | Evidence |
|---|---|---|---|
| Python / FastAPI | Yes | Yes | `/`, `/docs`, `/health`, `/v1/query` |
| Pydantic structured intent | Yes | Yes | Tests and query responses |
| LangGraph workflow | Yes | Yes | Full agent and E2E tests |
| Controlled SQL | Yes | Yes | SQLite and MySQL queries |
| Python analytics | Yes | Yes | YoY, CAGR, series and anomaly tests |
| SQLite | Yes | Yes | `.demo-data` isolated demo |
| MySQL 8.4 | Docker profile | Yes | 10 companies, 3 periods, 300 facts synced |
| Redis 7 | Docker profile | Yes | Session result stored and read back |
| FTS5 RAG | Yes | Yes | Citation with source, page and chunk |
| sqlite-vec vector search | Yes | Yes | Hybrid RRF retrieval |
| Chroma + BM25 | Optional local profile | Yes | Hashing fallback indexed 20 chunks |
| BGE-M3 embeddings | Optional | Configurable runtime | Set `EMBEDDING_API_KEY` and a compatible endpoint |
| OpenAI-compatible LLM API | Optional | Contract-tested | Chat request, auth, JSON mode and retry tests |
| Third-party Embedding API | Optional | Configurable runtime | Set `EMBEDDING_API_KEY` and a compatible endpoint |
| Local Ollama API | Optional | Documented adapter | OpenAI-compatible local base URL |
| Reranking | Yes | Yes | Lexical metadata reranker |
| MCP stdio | Yes | Yes | `financial_query` and `annual_report_search` |
| Docker Compose | Yes | Yes | API, MySQL and Redis healthy |
| Evaluation | Yes | Yes | Public demo 6 / 6 |
| Trace and fallback | Yes | Yes | `tool_events`, `validation`, `/health` |
| PDF ingestion | Optional | Unit-tested | Real LLM extraction requires a key |
| Async tasks | Yes | Yes | Evaluation task completed through API |

## Reproduce

```powershell
.\scripts\start-demo.ps1
.\scripts\evaluate-demo.ps1
python -m pytest -q
python -m ruff check src tests scripts
```

Chroma path:

```powershell
python -m pip install -e ".[dev,production-rag]"
.\scripts\start-demo.ps1 -RagBackend chroma
```

Docker path:

```powershell
docker compose up -d --build
docker compose ps
```
