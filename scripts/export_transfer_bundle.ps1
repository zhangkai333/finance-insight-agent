param(
    [Parameter(Mandatory = $true)]
    [string]$Destination,

    [switch]$IncludeSourceDocuments,
    [switch]$IncludeEnv,
    [switch]$IncludeDockerVolumes
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$destinationRoot = [System.IO.Path]::GetFullPath($Destination)

if ($destinationRoot -eq $projectRoot -or $destinationRoot.StartsWith($projectRoot + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Destination must be outside the project directory to avoid recursive copying."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$bundle = Join-Path $destinationRoot "finance-insight-transfer-$stamp"
New-Item -ItemType Directory -Force -Path $bundle | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $bundle "data") | Out-Null

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

if ($IncludeEnv) {
    $envPath = Join-Path $projectRoot ".env"
    if (Test-Path -LiteralPath $envPath) {
        Copy-Item -LiteralPath $envPath -Destination (Join-Path $bundle ".env") -Force
        Write-Warning "The bundle contains .env and must never be uploaded to GitHub or a public cloud link."
    }
}

if ($IncludeSourceDocuments) {
    $sourceDocuments = Join-Path $projectRoot "资料待放入"
    if (Test-Path -LiteralPath $sourceDocuments) {
        Copy-Item -LiteralPath $sourceDocuments -Destination (Join-Path $bundle "资料待放入") -Recurse -Force
        Write-Warning "The bundle contains third-party/competition documents. Keep it private and verify usage rights."
    }
}

if ($IncludeDockerVolumes) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "Docker CLI not found. Export the code/data bundle without -IncludeDockerVolumes, or install/start Docker."
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

$manifest = @()
Get-ChildItem -LiteralPath $bundle -Recurse -File | ForEach-Object {
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

@"
FinanceInsight transfer bundle
Created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")

This directory is for private device-to-device migration.
It may contain databases derived from licensed documents and, when explicitly requested, .env/API credentials.
Do not commit or upload it to a public GitHub repository.

On the laptop:
1. Clone the code repository.
2. Copy the data directory into the repository root.
3. If present, copy .env privately into the repository root.
4. Recreate the Python virtual environment; do not copy .venv.
5. Run scripts/import_transfer_bundle.ps1 -BundlePath <this directory>.
"@ | Set-Content -LiteralPath (Join-Path $bundle "README-TRANSFER.txt") -Encoding utf8

Write-Host "Transfer bundle created: $bundle"
Write-Host "Files are checksummed in manifest.sha256.json."
