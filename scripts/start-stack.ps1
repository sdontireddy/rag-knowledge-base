$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path

Set-Location $projectRoot

function Test-RequiredCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $CommandName"
    }
}

function Get-ConfigValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,

        [Parameter(Mandatory = $true)]
        [string]$DefaultValue
    )

    foreach ($line in Get-Content '.env') {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        if ($line.TrimStart().StartsWith('#')) {
            continue
        }

        $parts = $line.Split('=', 2)
        if ($parts.Count -ne 2) {
            continue
        }

        if ($parts[0].Trim() -eq $Key) {
            $value = $parts[1].Trim()
            if ($value) {
                return $value
            }
        }
    }

    return $DefaultValue
}

function Get-OllamaModels {
    $output = docker compose exec -T ollama ollama list
    $models = @()

    foreach ($line in ($output | Select-Object -Skip 1)) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $model = ($line -split '\s+')[0]
        if ($model) {
            $models += $model
        }
    }

    return $models
}

function Ensure-Model {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Model
    )

    $models = Get-OllamaModels
    $altModel = $null

    if ($Model -notmatch ':') {
        $altModel = "$Model`:latest"
    }

    if ($models -contains $Model) {
        Write-Host "Model already present in ollama volume: $Model"
        return
    }

    if ($altModel -and ($models -contains $altModel)) {
        Write-Host "Model already present in ollama volume: $altModel"
        return
    }

    Write-Host "Model missing, pulling: $Model"
    docker compose exec -T ollama ollama pull $Model
}

Test-RequiredCommand -CommandName 'docker'

docker compose version | Out-Null

if (-not (Test-Path '.env')) {
    if (-not (Test-Path '.env.example')) {
        throw 'Missing .env.example, cannot bootstrap configuration.'
    }

    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example'
}

$llmModel = Get-ConfigValue -Key 'LLM_MODEL' -DefaultValue 'tinyllama:latest'
$embeddingModel = Get-ConfigValue -Key 'EMBEDDING_MODEL' -DefaultValue 'nomic-embed-text'

Write-Host 'Starting base services (ollama + chromadb)...'
docker compose up -d ollama chromadb

Write-Host 'Waiting for Ollama to be ready...'
for ($attempt = 1; $attempt -le 60; $attempt++) {
    docker compose exec -T ollama ollama list *> $null
    if ($LASTEXITCODE -eq 0) {
        break
    }

    Start-Sleep -Seconds 2

    if ($attempt -eq 60) {
        throw 'Ollama did not become ready in time.'
    }
}

Ensure-Model -Model $llmModel
Ensure-Model -Model $embeddingModel

Write-Host 'Starting app services (api + wrapper-api + ui)...'
docker compose up -d api wrapper-api ui

Write-Host 'Stack is up.'
docker compose ps