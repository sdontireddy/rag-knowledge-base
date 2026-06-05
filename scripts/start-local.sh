#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting local stack (ollama + chromadb + api + ui)..."
bash "${SCRIPT_DIR}/start-stack.sh"

echo "Running initial ingestion..."
bash "${SCRIPT_DIR}/run-ingestion.sh"

echo "Local stack and ingestion are ready."
