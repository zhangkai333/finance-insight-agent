# Evaluation

## Public Demo Dataset

`evals/dataset_demo.json` is the default evaluation set for the public repository.
It uses synthetic data and covers:

- point query;
- trend statistics;
- ranking;
- RAG attribution;
- chart generation;
- comprehensive multi-metric analysis.

The current deterministic result is:

| Metric | Result |
|---|---:|
| Cases | 6 |
| Task success rate | 100% |
| Intent accuracy | 100% |
| Tool selection accuracy | 100% |
| Citation coverage | 100% |
| SQL numeric exact match | 100% |

Latency measurements vary by machine. Use the generated report rather than a
hard-coded performance claim.

## Test Isolation

`tests/conftest.py` creates a temporary synthetic database for every test run.
The public test suite therefore does not read the maintainer's private
`data/finance_insight.sqlite3` or `data/rag.sqlite3`.

Current checks:

```powershell
python -m pytest -q
python -m ruff check src tests scripts
.\scripts\evaluate-demo.ps1
```

Expected public results:

- 72 tests passed when the `production-rag` extra is installed;
- 71 tests passed and the optional Chroma test is skipped with the minimal `dev`
  extra;
- Ruff reports no issues;
- Demo regression set reaches 6 / 6.

## Private Regression Data

Private real-data baselines and human-review exports are not included in the
public repository. Regenerate them from an authorized local database before
use. Do not publish private report text, raw PDFs, or derived databases without
license review.

## Metrics

The evaluator reports:

- intent accuracy;
- tool selection accuracy;
- SQL numeric exact match;
- citation coverage;
- chart count;
- plan strategy;
- validation status;
- clarification behavior;
- task success rate;
- latency percentiles.

These metrics are regression checks, not proof of real-user generalization.
Future work should add retrieval Recall@K, nDCG, citation faithfulness review,
and a human-reviewed financial analysis set.

## Test Layers

- Unit: intent parsing, structured output, LLM client, retry, stores, MySQL
  loader, concurrency, and individual tools.
- Integration: LangGraph, FastAPI, MCP stdio, hybrid retrieval, failure
  injection, and demo initialization.
- E2E: a complete multi-metric question must return facts, calculations,
  citations, and charts.

MySQL, Redis, Docker runtime, and the Chroma hashing/BM25 path were validated
in the current workspace. A real LLM provider and remote BGE-M3 embedding still
require credentials and should be validated separately.
