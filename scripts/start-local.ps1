$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host 'Starting local stack (ollama + chromadb + api + ui)...'
& (Join-Path $scriptDir 'start-stack.ps1')

Write-Host 'Running initial ingestion...'
docker compose run --rm --build ingestion

Write-Host 'Local stack and ingestion are ready.'
