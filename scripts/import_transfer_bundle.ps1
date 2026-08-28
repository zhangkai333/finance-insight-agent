param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,

    [switch]$CopyEnv,
    [switch]$CopySourceDocuments,
    [switch]$RestoreMySql
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bundle = (Resolve-Path -LiteralPath $BundlePath).Path

if ($bundle -eq $projectRoot -or $projectRoot.StartsWith($bundle + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "BundlePath must not be the project itself or a parent of the project."
}

# This switch is retained only so older commands fail safely.
if ($CopyEnv) {
    throw "For security, importing .env is disabled. Create .env from .env.example on the laptop and do not reuse the company-computer DeepSeek API key."
}

$manifestPath = Join-Path $bundle "manifest.sha256.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "manifest.sha256.json not found in bundle."
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
foreach ($item in $manifest) {
    $path = Join-Path $bundle $item.path
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing bundle file: $($item.path)" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne $item.sha256) { throw "Checksum mismatch: $($item.path)" }
}
Write-Host "Checksum verification passed."

$dataSource = Join-Path $bundle "data"
if (Test-Path -LiteralPath $dataSource) {
    $dataTarget = Join-Path $projectRoot "data"
    New-Item -ItemType Directory -Force -Path $dataTarget | Out-Null
    Get-ChildItem -LiteralPath $dataSource -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $dataTarget -Recurse -Force
    }
}

if ($CopySourceDocuments) {
    $sourceDocuments = Join-Path $bundle "资料待放入"
    if (-not (Test-Path -LiteralPath $sourceDocuments)) { throw "Bundle does not contain source documents." }
    $targetDocuments = Join-Path $projectRoot "资料待放入"
    if (Test-Path -LiteralPath $targetDocuments) {
        throw "Target source-document directory already exists. Move/rename it before importing to avoid accidental overwrite."
    }
    Copy-Item -LiteralPath $sourceDocuments -Destination $targetDocuments -Recurse
}

if ($RestoreMySql) {
    $dump = Join-Path $bundle "docker-volumes/mysql.sql"
    if (-not (Test-Path -LiteralPath $dump)) { throw "Bundle does not contain docker-volumes/mysql.sql." }
    docker compose -f (Join-Path $projectRoot "docker-compose.yml") up -d mysql
    Get-Content -Raw -LiteralPath $dump | docker compose -f (Join-Path $projectRoot "docker-compose.yml") exec -T mysql `
        sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
}

Write-Host "Bundle imported into: $projectRoot"
Write-Host "The import did not copy .env or API keys."
Write-Host "Next: recreate .venv, install dependencies, run tests, then start the API."
