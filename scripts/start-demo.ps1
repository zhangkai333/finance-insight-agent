param(
    [int]$Port = 8000,
    [ValidateSet("sqlite", "chroma")]
    [string]$RagBackend = "sqlite",
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

$hasFinance = Test-Path -LiteralPath $financeDb
$hasRag = Test-Path -LiteralPath $ragDb
if ($RefreshData -or (-not $hasFinance -and -not $hasRag)) {
    & $python (Join-Path $root "scripts\init_demo_data.py") --data-dir $demoDir --force
}
elseif (-not $hasFinance -or -not $hasRag) {
    throw "Only one demo database exists in .demo-data. Delete that directory or rerun with -RefreshData."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $root "src"
$env:DEMO_MODE = "true"
$env:FINANCE_BACKEND = "sqlite"
$env:RAG_BACKEND = $RagBackend
$env:FINANCE_DB = $financeDb
$env:RAG_DB = $ragDb
$env:ARTIFACT_DIR = Join-Path $demoDir "artifacts"
$env:LOG_DIR = Join-Path $demoDir "logs"
$env:EVAL_DATASET = Join-Path $root "evals\dataset_demo.json"
$env:EVAL_OUTPUT = Join-Path $demoDir "evaluation\report.json"
$env:UPLOAD_DATABASE_PATH = Join-Path $demoDir "legacy\finagent_runtime.db"
$env:CHROMA_PATH = Join-Path $demoDir "chroma"
$env:CHROMA_COLLECTION = "finance_insight_demo"

Set-Location $root
if ($RagBackend -eq "chroma") {
    Write-Host "Indexing the synthetic demo corpus into Chroma."
    & $python (Join-Path $root "scripts\index_demo_chroma.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Chroma indexing failed. Install optional dependencies with: .\.venv\Scripts\python.exe -m pip install -e '.[dev,production-rag]'"
    }
}

Write-Host "FinanceInsight synthetic demo: http://127.0.0.1:$Port"
& $python -m uvicorn finance_insight.api:app --host 127.0.0.1 --port $Port
