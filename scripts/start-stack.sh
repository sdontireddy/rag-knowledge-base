#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

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

ensure_model "llama3.1:8b"
ensure_model "nomic-embed-text"

echo "Starting app services (api + ui)..."
docker compose up -d api ui

echo "Stack is up."
docker compose ps
