# RAG Knowledge Base (Local)

My Own personal Local Docker-based RAG stack for indexing markdown notes and searching them semantically , planning to include step by step brain mapping and trade off

## What Runs

- `ollama` on port `11434`
- `chromadb` on port `8000` (pinned Docker image tag)
- `api` on port `8080`
- `ui` on port `8501`
- `ingestion` (one-shot pipeline container)

## Prerequisites

- Docker Desktop (Compose V2)
- Bash or PowerShell

## 1. Open Project

```bash
cd /c/Repo/sdontireddy/Projects/rag-knowledge-base
```

## 2. Create Environment File

```bash
cp .env.example .env
```

If you want a different ChromaDB Docker version, change this in `.env`:

```bash
CHROMADB_IMAGE_TAG=0.5.5
```

## 3. Start Core Services

```bash
docker compose up -d ollama chromadb api ui
```

Optional: view logs

```bash
docker compose logs -f api
```

## 4. Pull Ollama Models

Pull both models used by this project:

```bash
curl -X POST http://localhost:11434/api/pull -d '{"name":"llama3:8b"}'
curl -X POST http://localhost:11434/api/pull -d '{"name":"nomic-embed-text"}'
```

## 5. Add Documents for Ingestion

Put markdown files under:

- `knowledge_base/AWS`
- `knowledge_base/LULU`
- `knowledge_base/Techno`
- `knowledge_base/MAWM`

You can change domain folders with `SOURCE_DIRS` in `.env`.

## 6. Run Ingestion

Run pipeline as a one-shot container:

```bash
bash scripts/run-ingestion.sh
```

Expected output includes report file write to:

- `reports/ingestion_report.json` on the host (configurable via `HOST_INGESTION_REPORT_PATH`)

Incremental behavior:

- The first run ingests all discovered markdown files.
- Later runs read the previous ingestion report timestamp and skip files whose modified time is not newer than that baseline.
- Set `INGESTION_MIN_FILE_DELTA_SECONDS` in `.env` if you want a buffer before a recently modified file is considered eligible for re-ingestion.
- When a file is re-ingested, existing vectors for that source file are removed first so stale chunks do not accumulate.

## 7. Verify Services

API Reference:

- Swagger-style document: `docs/api-swagger-style.md`
- Live OpenAPI docs: `http://localhost:8080/docs`

Health:

```bash
curl http://localhost:8080/api/health
```

Domains:

```bash
curl http://localhost:8080/api/domains
```

Search:

```bash
curl -X POST http://localhost:8080/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"bedrock","k":5,"domain_filter":["AWS"],"min_score":0.0}'
```

Answer generation:

```bash
curl -X POST http://localhost:8080/api/answer \
  -H "Content-Type: application/json" \
  -d '{"query":"How do I enable Bedrock?","k":5,"domain_filter":["AWS"],"max_tokens":512}'
```

Grounding rules for `/api/answer`:

- Answers are built from retrieved vector-store chunks only.
- If the model returns uncited or invalid content, the API downgrades the response to `INSUFFICIENT_CONTEXT`.
- Citations are restricted to chunk IDs that were actually retrieved for that request.

UI:

- Open `http://localhost:8501` to ask grounded questions and inspect citations.

## 8. Run Tests

```bash
/c/Repo/sdontireddy/MyNotes/.venv/Scripts/python -m pytest tests/unit tests/integration/test_ingestion_pipeline.py -q
```

## 9. Stop Stack

```bash
docker compose down
```

Remove volumes too:

```bash
docker compose down -v
```

## Notes

- ChromaDB runs as a Docker service (`chromadb`), not as a local host process.
- API ingest endpoints are not exposed yet; ingestion is currently executed via `docker compose run --rm ingestion`.
- Memory constrains forced us to use tinyllama:latest
- Increased TimeOut , also proper error messaging

## TODO

### Infra Improvements

1.  Create Startup Script - DONE
2.  Update Docker Compose - DONE
    - Check the Ollama volume if exists or not
3.  Pre-requisite tests to make sure all the require models are available and HEARTBEATS are accesible - DONE

#### Embeddings

- Curently only markdown file support
- Future
  - Image
  - PDF
  - Q: To keep apps modular , Can we have seprate PDF PDF-RAG-KNOWLDGE-BASE tool and IMAGE-RAG-KNOWLDGE-BASE etc

##### Optimizations

- How to improve the ranking for relvant information
  - Currently search results are OK , we need to make them better
  - Structure the knowledge base
    - Markdown explore a better template / tagging/ metadata
- Currently on local setup , so latencies very high
  - Deploy this in a PROD like machine and benchmark
- No specific Guardrails yet
- Check if we can need to tweek the config for Ollama - DONE
  - **RCA** : generation fails because llama3:8b needs more RAM than available to Ollama in Docker , so switched to tinyllama:latest
- Play with Tokens size , retreived Chunks

#### Documentations

- Swagger for API - DONE
- Update Tradeoffs and create a brain map
