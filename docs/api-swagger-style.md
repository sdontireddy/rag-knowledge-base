# RAG Knowledge Base API (Swagger-Style Reference)

Base URL: `http://localhost:8080`

## OpenAPI UI

This FastAPI app also exposes built-in interactive docs:

- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
- OpenAPI JSON: `http://localhost:8080/openapi.json`

## Tags

- `health`
- `search`

---

## GET /healthz

Lightweight liveness check.

### Response `200`

```json
{
  "status": "ok"
}
```

---

## GET /api/health

Checks external dependencies and vector store status.

### Response `200`

```json
{
  "status": "healthy",
  "services": {
    "ollama": "up",
    "chromadb": "up"
  },
  "vector_store_count": 303,
  "checked_at": "2026-05-28T21:03:50.123456Z"
}
```

### Fields

- `status`: `healthy | degraded`
- `services.ollama`: `up | down`
- `services.chromadb`: `up | down`
- `vector_store_count`: integer
- `checked_at`: ISO timestamp

---

## GET /api/domains

Returns aggregated domain stats from indexed chunks.

### Response `200`

```json
{
  "domains": [
    {
      "name": "AWS",
      "document_count": 3,
      "chunk_count": 27
    },
    {
      "name": "Interviews",
      "document_count": 35,
      "chunk_count": 190
    }
  ]
}
```

---

## POST /api/search

Semantic search over indexed chunks.

### Request Body

```json
{
  "query": "bedrock setup",
  "k": 5,
  "domain_filter": ["AWS"],
  "min_score": 0.0
}
```

### Request Schema

- `query` (string, required, min length 1)
- `k` (int, optional, default 5, range 1-25)
- `domain_filter` (string array, optional)
- `min_score` (float, optional, default 0.0, range 0.0-1.0)

### Response `200`

```json
{
  "query": "bedrock setup",
  "results": [
    {
      "chunk_id": "AWS:Bedrock.md:12:0",
      "text": "...",
      "source_path": "AWS/Bedrock.md",
      "domain": "AWS",
      "section": "Setup",
      "relevance_score": 0.92
    }
  ]
}
```

### Error `503`

```json
{
  "detail": "Search service is unavailable"
}
```

---

## POST /api/answer

Retrieves relevant chunks and generates an answer with citations.

### Request Body

```json
{
  "query": "How do I enable Bedrock?",
  "k": 5,
  "domain_filter": ["AWS"],
  "max_tokens": 512
}
```

### Request Schema

- `query` (string, required, min length 1)
- `k` (int, optional, default 5, range 1-25)
- `domain_filter` (string array, optional)
- `max_tokens` (int, optional, default 1024, range 64-4096)

### Response `200`

```json
{
  "query": "How do I enable Bedrock?",
  "answer_text": "Use IAM permissions and model access in Bedrock console...",
  "citations": [
    {
      "chunk_id": "AWS:Bedrock.md:12:0",
      "source_path": "AWS/Bedrock.md",
      "domain": "AWS",
      "section": "Setup",
      "relevance_score": 0.92
    }
  ],
  "context_chunks": [
    {
      "chunk_id": "AWS:Bedrock.md:12:0",
      "text": "...",
      "source_path": "AWS/Bedrock.md",
      "domain": "AWS",
      "section": "Setup",
      "relevance_score": 0.92
    }
  ],
  "model": "tinyllama:latest",
  "generation_time_ms": 1320
}
```

### Error `503`

```json
{
  "detail": "Answer service is unavailable"
}
```

---

## Notes

- Ingestion APIs are not currently exposed via HTTP endpoints in this app.
- Ingestion is run as a one-shot Docker Compose workflow using `bash scripts/run-ingestion.sh`.
