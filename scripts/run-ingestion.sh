#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing .env file at ${ENV_FILE}"
  exit 1
fi

source "${ENV_FILE}"

HOST_KNOWLEDGE_BASE_ROOT="${HOST_KNOWLEDGE_BASE_ROOT:-..}"
HOST_INGESTION_REPORT_PATH="${HOST_INGESTION_REPORT_PATH:-${PROJECT_ROOT}/reports/ingestion_report.json}"
SOURCE_DIRS="${SOURCE_DIRS:-}"
KNOWLEDGE_BASE_ROOT="${KNOWLEDGE_BASE_ROOT:-/app/knowledge_base}"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"

cd "${PROJECT_ROOT}"

resolve_host_root() {
  local raw_path="$1"

  if [[ "$raw_path" = /* ]] || [[ "$raw_path" =~ ^[A-Za-z]:[\\/] ]]; then
    printf '%s\n' "$raw_path"
  else
    (cd "${PROJECT_ROOT}/${raw_path}" && pwd)
  fi
}

HOST_ROOT="$(resolve_host_root "$HOST_KNOWLEDGE_BASE_ROOT")"

if [[ "$HOST_INGESTION_REPORT_PATH" = /* ]] || [[ "$HOST_INGESTION_REPORT_PATH" =~ ^[A-Za-z]:[\\/] ]]; then
  REPORT_HOST_PATH="$HOST_INGESTION_REPORT_PATH"
else
  REPORT_HOST_PATH="${PROJECT_ROOT}/${HOST_INGESTION_REPORT_PATH}"
fi

REPORT_FILE_NAME="$(basename "$REPORT_HOST_PATH")"
CONTAINER_REPORT_DIR="/app/reports"
CONTAINER_REPORT_PATH="${CONTAINER_REPORT_DIR}/${REPORT_FILE_NAME}"

if [[ ! -d "$HOST_ROOT" ]]; then
  echo "HOST_KNOWLEDGE_BASE_ROOT does not exist or is not a directory: $HOST_ROOT"
  exit 1
fi

IFS=',' read -r -a source_dir_array <<< "$SOURCE_DIRS"
if [[ ${#source_dir_array[@]} -eq 0 ]]; then
  echo "SOURCE_DIRS is empty."
  exit 1
fi

echo "Validating ingestion sources under host root: $HOST_ROOT"

for raw_dir in "${source_dir_array[@]}"; do
  source_dir="$(echo "$raw_dir" | xargs)"
  if [[ -z "$source_dir" ]]; then
    continue
  fi

  host_dir="$HOST_ROOT/$source_dir"

  if [[ ! -d "$host_dir" ]]; then
    echo "Configured source directory is missing: $host_dir"
    exit 1
  fi

  markdown_count=$(find "$host_dir" -type f \( -iname '*.md' -o -iname '*.markdown' \) | wc -l | tr -d ' ')
  if [[ "$markdown_count" == "0" ]]; then
    echo "No markdown files found in configured source directory: $host_dir"
    exit 1
  fi

  echo "Validated $source_dir: $markdown_count markdown files"
done

echo "Container knowledge base root: $KNOWLEDGE_BASE_ROOT"
echo "Host ingestion report target: $REPORT_HOST_PATH"
echo "Starting ingestion prerequisites (ollama + chromadb)..."
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

alt_embedding_model=""
if [[ "$EMBEDDING_MODEL" != *:* ]]; then
  alt_embedding_model="${EMBEDDING_MODEL}:latest"
fi

if docker compose exec -T ollama ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$EMBEDDING_MODEL"; then
  echo "Embedding model already present in ollama volume: $EMBEDDING_MODEL"
elif [[ -n "$alt_embedding_model" ]] && docker compose exec -T ollama ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$alt_embedding_model"; then
  echo "Embedding model already present in ollama volume: $alt_embedding_model"
else
  echo "Embedding model missing, pulling: $EMBEDDING_MODEL"
  docker compose exec -T ollama ollama pull "$EMBEDDING_MODEL"
fi

REPORT_HOST_DIR_RAW="$(dirname "$REPORT_HOST_PATH")"
mkdir -p "$REPORT_HOST_DIR_RAW"
REPORT_HOST_DIR="$(cd "$REPORT_HOST_DIR_RAW" && pwd)"

echo "Running ingestion..."
MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' docker compose run --rm --build \
  -e "INGESTION_REPORT_PATH=${CONTAINER_REPORT_PATH}" \
  -v "${REPORT_HOST_DIR}:${CONTAINER_REPORT_DIR}" \
  ingestion

if [[ -f "$REPORT_HOST_PATH" ]]; then
  echo "Ingestion report copied to host: $REPORT_HOST_PATH"
else
  echo "Ingestion completed but report was not found at: $REPORT_HOST_PATH"
  exit 1
fi
