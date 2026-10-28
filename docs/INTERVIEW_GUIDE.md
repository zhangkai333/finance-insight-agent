# FinanceInsight Agent Interview Demo

## One-Sentence Introduction

FinanceInsight Agent is a traceable financial-analysis workflow that turns a
natural-language question into controlled SQL facts, deterministic Python
calculations, citation-bearing RAG evidence, charts, and an inspectable tool
trace.

## 90-Second Explanation

The project targets recurring analyst work: finding financial facts, comparing
multiple years, and locating explanations in annual reports. The input is a
question and optional session ID. A deterministic parser first builds a typed
`QueryIntent`; LangGraph then routes the request to SQL, Python analysis, RAG,
chart generation, validation, and final synthesis.

The key design decision is that the LLM is not the source of financial numbers.
SQL provides facts, Python performs calculations, and RAG returns source text
with page numbers. The model is limited to understanding and expression. If
evidence is missing, the workflow returns `partial` instead of inventing an
explanation.

The public repository runs on synthetic data so it can be cloned safely. Real
annual reports and derived databases are intentionally excluded. The verified
public baseline includes 72 passing tests, Ruff checks, and a 6/6 deterministic
Demo regression set.

## Demo Sequence

Start the isolated public demo:

```powershell
.\scripts\start-demo.ps1
```

Open `http://127.0.0.1:8000` and run these in order:

| Step | Question | What to show |
|---|---|---|
| 1 | `查询凯莱英2024年营业收入` | Structured fact, unit, SQL trace |
| 2 | `统计凯莱英2022到2024年营业收入趋势` | Python YoY and CAGR calculations |
| 3 | `分析凯莱英2022到2024年营业收入异常变化并解释原因` | Anomaly detection, RAG citation, validation |
| 4 | `绘制凯莱英2022到2024年营业收入趋势图` | Chart generated from verified series |
| 5 | `请查询某个公司的情况` | Clarification instead of tool execution |

Then open `/health` and point out:

- `demo_mode=true`;
- effective SQLite and RAG backends;
- memory store;
- no external LLM key required.

## Architecture Talking Points

1. `QueryIntent` is a Pydantic model, so malformed structured output is rejected
   before tools run.
2. SQL uses fixed templates and bound parameters. The model cannot inject free
   SQL text.
3. The analysis tool calculates YoY, CAGR, and simple anomalies in Python.
4. RAG filters by company and year, merges FTS and vector candidates, reranks,
   and returns file/page/chunk metadata.
5. Validation separately checks fact coverage, numeric types, calculation
   traces, citation coverage, and cause evidence.
6. Failures remain visible through `status`, `errors`, `fallback_used`,
   `tool_events`, and `execution_context`.

## High-Frequency Questions

**Why not let the model answer directly?**

Financial numbers need deterministic retrieval and calculation. The model can
misread tables or invent explanations. SQL and Python keep facts and arithmetic
reproducible, while RAG supplies bounded textual evidence.

**Why LangGraph instead of a simple chain?**

The workflow has conditional routing: clarification, calculation, RAG, charts,
and validation are optional. Graph state and conditional edges make those paths
explicit and testable.

**How is SQL safety enforced?**

The LLM cannot submit SQL. It can only propose allowlisted companies, years, and
metrics. The tool constructs parameterized queries from that typed intent.

**Does the project call external model APIs?**

Yes. The application includes an OpenAI-compatible Chat Completions client and an
OpenAI-compatible Embeddings client. They support Bearer authentication,
timeouts, retries, batching and deterministic fallback. The public demo does not
require a key, and the same code can target a local Ollama endpoint, DeepSeek,
SiliconFlow, OpenAI or another compatible provider. See
`docs/API_INTEGRATION.md` for configuration and verification commands.

**How do you know RAG is correct?**

The current checks verify metric evidence, cause wording, page metadata, and
citation coverage. This is not a full faithfulness guarantee. The next step is
chunk-level Recall@K, nDCG, and human citation review.

**What is still incomplete?**

The public demo uses synthetic data. MySQL, Redis, Docker, MCP, and Chroma with
hashing embeddings were validated locally. The same workflow can enable a
compatible LLM and Embedding provider through environment variables. The public
CI stays in deterministic mode so no credentials or paid API calls are needed;
authorization and production observability remain separate hardening work.

## Claims to Avoid

Do not claim:

- production-grade financial accuracy;
- that synthetic values are real company results;
- that every optional integration has been end-to-end tested;
- that citation coverage proves causal explanations;
- that the project supports unrestricted NL2SQL or autonomous multi-agent
  execution.

## Next Engineering Steps

1. Add human-reviewed citation faithfulness data.
2. Evaluate retrieval with Recall@K, MRR, and nDCG.
3. Pin and lock the complete dependency graph.
4. Validate MySQL/Redis and Docker runtime in CI.
5. Add authentication, RBAC, audit logging, and cost monitoring.
