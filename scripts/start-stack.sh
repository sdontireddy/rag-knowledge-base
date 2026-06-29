#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name"
    exit 1
  fi
}

require_command docker

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose V2 is required and was not found."
  exit 1
fi

if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    echo "Missing .env.example, cannot bootstrap configuration."
    exit 1
  fi

  cp .env.example .env
  echo "Created .env from .env.example"
fi

set -a
source .env
set +a

LLM_MODEL="${LLM_MODEL:-tinyllama:latest}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"

echo "Starting base services (ollama + chromadb)..."
docker compose up -d ollama chromadb

echo "Waiting for Ollama to be ready..."
for i in {1..60}; do
  if docker compose exec -T ollama ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "$i" == "60" ]]; then
    echo "Ollama did not become ready in time."
    exit 1
  fi
done

ensure_model() {
  local model="$1"
  local alt_model=""

  if [[ "$model" != *:* ]]; then
    alt_model="${model}:latest"
  fi

  if docker compose exec -T ollama ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    echo "Model already present in ollama volume: $model"
  elif [[ -n "$alt_model" ]] && docker compose exec -T ollama ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$alt_model"; then
    echo "Model already present in ollama volume: $alt_model"
  else
    echo "Model missing, pulling: $model"
    docker compose exec -T ollama ollama pull "$model"
  fi
}

ensure_model "$LLM_MODEL"
ensure_model "$EMBEDDING_MODEL"

echo "Starting app services (api + wrapper-api + ui)..."
docker compose up -d api wrapper-api ui

echo "Stack is up."
docker compose ps
