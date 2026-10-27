# FinanceInsight Agent Product Requirements

## Problem

Financial analysts repeatedly switch between annual reports, spreadsheets, SQL
queries, and charting tools. This creates three recurring risks:

- numbers are copied or calculated inconsistently;
- explanations lose their original page and source context;
- tool failures and incomplete evidence are hidden in the final answer.

## Product Goal

Build a traceable assistant that answers financial questions with:

- structured facts from a controlled database;
- deterministic calculations in Python;
- citation-bearing source text for explanations;
- charts based only on verified series;
- explicit validation, retry, fallback, and tool traces.

## User Workflow

```text
Question
-> typed intent
-> task plan
-> SQL fact query
-> Python analysis
-> annual-report retrieval when explanation is requested
-> chart generation when requested
-> evidence validation
-> answer plus citations and trace
```

## Supported Demo Scenarios

1. Point query for one company, year, and metric.
2. Multi-year trend, YoY, CAGR, and anomaly detection.
3. Multi-metric and multi-company questions.
4. Annual-report evidence retrieval with company/year filtering.
5. Citation-bearing explanation or an explicit partial result when evidence is
   insufficient.
6. Chart generation from verified analysis series.
7. Session continuation and asynchronous evaluation tasks.

## Public Data Policy

The public repository uses fully synthetic data.

- Company names and stock codes are retained for interface compatibility.
- Every generated fact is marked `synthetic_demo_only`.
- Synthetic narrative text is marked as not being a real annual report.
- Private reports, PDFs, derived databases and API keys are not distributed.

## Non-Goals

- investment advice;
- unrestricted model-generated SQL;
- autonomous multi-agent execution;
- production authorization and RBAC;
- claims of human-grade financial analysis accuracy;
- OCR or complex-table extraction validated against real filings.

## Acceptance Criteria

- Fresh clone can start the public demo without private data.
- SQL, calculations, RAG, charts and clarification paths execute.
- The RAG path returns file, year, page and chunk metadata.
- Tests do not read maintainer-private databases.
- Full public test suite, Ruff, RAG index verification and demo evaluation pass.
- Docker Compose runs API, MySQL and Redis with health checks and data sync.
- Optional Chroma + BM25 and MCP stdio paths are executable.
