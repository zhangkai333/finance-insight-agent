param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,

    [switch]$IncludeSourceDocuments,
    [switch]$IncludeAllLocalData,
    [switch]$IncludeEnv,
    [switch]$IncludeDockerVolumes
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$destinationRoot = [System.IO.Path]::GetFullPath($Destination)

if ($destinationRoot -eq $projectRoot -or $destinationRoot.StartsWith($projectRoot + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Destination must be outside the project directory to avoid recursive copying."
}

# This switch is retained only so older commands fail safely instead of silently
# copying credentials. Laptop handover must never include .env or API keys.
if ($IncludeEnv) {
    throw "For security, exporting .env is disabled. Create a new .env from .env.example on the laptop and keep DEEPSEEK_API_KEY empty or use a newly issued key."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$bundle = Join-Path $destinationRoot "finance-insight-transfer-$stamp"
New-Item -ItemType Directory -Force -Path $bundle | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bundle "data") | Out-Null

if ($IncludeAllLocalData) {
    $dataSource = Join-Path $projectRoot "data"
    $dataTarget = Join-Path $bundle "data"
    if (Test-Path -LiteralPath $dataSource) {
        Get-ChildItem -LiteralPath $dataSource -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $dataTarget -Recurse -Force
        }
    }
} else {
    $files = @(
        "data/finance_insight.sqlite3",
        "data/rag.sqlite3"
    )

    foreach ($relative in $files) {
        $source = Join-Path $projectRoot $relative
        if (Test-Path -LiteralPath $source) {
            $target = Join-Path $bundle $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }
}

if ($IncludeSourceDocuments) {
    $sourceDocuments = Join-Path $projectRoot "资料待放入"
    if (Test-Path -LiteralPath $sourceDocuments) {
        Copy-Item -LiteralPath $sourceDocuments -Destination (Join-Path $bundle "资料待放入") -Recurse -Force
        Write-Warning "The bundle contains private source/competition documents. Keep it on a trusted removable drive and do not upload it to GitHub or a public cloud link."
    }
}

if ($IncludeDockerVolumes) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "Docker CLI not found. Export without -IncludeDockerVolumes, or install/start Docker first."
    }
    $volumeDir = Join-Path $bundle "docker-volumes"
    New-Item -ItemType Directory -Force -Path $volumeDir | Out-Null
    docker compose -f (Join-Path $projectRoot "docker-compose.yml") exec -T mysql `
        sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --events "$MYSQL_DATABASE"' `
        | Set-Content -LiteralPath (Join-Path $volumeDir "mysql.sql") -Encoding utf8
    docker compose -f (Join-Path $projectRoot "docker-compose.yml") exec -T redis redis-cli SAVE | Out-Null
    $redisContainer = docker compose -f (Join-Path $projectRoot "docker-compose.yml") ps -q redis
    if ($redisContainer) {
        docker cp "${redisContainer}:/data/dump.rdb" (Join-Path $volumeDir "redis-dump.rdb")
    }
}

@"
FinanceInsight private laptop handover bundle
Created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")

This directory is for a one-time private device-to-device migration.
It intentionally does NOT contain .env or API credentials.
Do not commit this directory or upload it to GitHub/public cloud storage.

On the laptop:
1. Clone the code repository from GitHub.
2. Recreate the Python virtual environment; do not copy .venv.
3. Create .env from .env.example. Keep DEEPSEEK_API_KEY empty or use a newly issued key.
4. Run scripts/import_transfer_bundle.ps1 -BundlePath <this directory> -CopySourceDocuments.
5. Run the test suite before deleting anything from the old computer.
"@ | Set-Content -LiteralPath (Join-Path $bundle "README-TRANSFER.txt") -Encoding utf8

$manifest = @()
Get-ChildItem -LiteralPath $bundle -Recurse -File | Where-Object { $_.Name -ne "manifest.sha256.json" } | ForEach-Object {
    $relativePath = $_.FullName.Substring($bundle.Length)
    while ($relativePath.StartsWith("\") -or $relativePath.StartsWith("/")) {
        $relativePath = $relativePath.Substring(1)
    }
    $manifest += [PSCustomObject]@{
        path = $relativePath
        bytes = $_.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    }
}
$manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $bundle "manifest.sha256.json") -Encoding utf8

Write-Host "Transfer bundle created: $bundle"
Write-Host "The bundle intentionally excludes .env and API keys."
Write-Host "Files are checksummed in manifest.sha256.json."
