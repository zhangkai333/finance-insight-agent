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

$manifestPath = Join-Path $bundle "manifest.sha256.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "manifest.sha256.json not found in bundle."
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
foreach ($item in $manifest) {
    if ($item.path -in @("manifest.sha256.json", "README-TRANSFER.txt")) { continue }
    $path = Join-Path $bundle $item.path
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing bundle file: $($item.path)" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actual -ne $item.sha256) { throw "Checksum mismatch: $($item.path)" }
}
Write-Host "Checksum verification passed."

$dataSource = Join-Path $bundle "data"
if (Test-Path -LiteralPath $dataSource) {
    New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot "data") | Out-Null
    Get-ChildItem -LiteralPath $dataSource -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path (Join-Path $projectRoot "data") $_.Name) -Force
    }
}

if ($CopyEnv) {
    $sourceEnv = Join-Path $bundle ".env"
    if (-not (Test-Path -LiteralPath $sourceEnv)) { throw "Bundle does not contain .env." }
    Copy-Item -LiteralPath $sourceEnv -Destination (Join-Path $projectRoot ".env") -Force
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
Write-Host "Next: recreate .venv, install dependencies, run tests, then start Docker/API."
