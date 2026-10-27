param(
    [switch]$RefreshData
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$demoDir = Join-Path $root ".demo-data"
$financeDb = Join-Path $demoDir "finance_insight.sqlite3"
$ragDb = Join-Path $demoDir "rag.sqlite3"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found. Run: py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e '.[dev]'"
}

if ($RefreshData -or -not (Test-Path -LiteralPath $financeDb) -or -not (Test-Path -LiteralPath $ragDb)) {
    & $python (Join-Path $root "scripts\init_demo_data.py") --data-dir $demoDir --force
}

$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $root "src"
$env:DEMO_MODE = "true"
$env:FINANCE_BACKEND = "sqlite"
$env:RAG_BACKEND = "sqlite"
$env:FINANCE_DB = $financeDb
$env:RAG_DB = $ragDb
$env:ARTIFACT_DIR = Join-Path $demoDir "artifacts"
$env:LOG_DIR = Join-Path $demoDir "logs"
$env:EVAL_DATASET = Join-Path $root "evals\dataset_demo.json"
$env:EVAL_OUTPUT = Join-Path $demoDir "evaluation\report.json"

Set-Location $root
& $python -m finance_insight.evaluation --dataset $env:EVAL_DATASET --output $env:EVAL_OUTPUT
