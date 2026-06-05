# RAG Knowledge Base (Local)

This is a local Docker-based RAG stack for indexing markdown notes and searching them semantically. It uses Ollama, ChromaDB, FastAPI, and Streamlit to show the full flow end-to-end: ingestion, embeddings, vector search, retrieval, grounded answer generation, and citations.

This project is for engineers who want to understand a local RAG stack end-to-end.
It is not intended as a production-ready enterprise RAG platform.

## Who This Is For

- Developers learning local RAG architecture
- Engineers who want a Docker + Ollama + ChromaDB reference implementation
- People who want to understand the full flow instead of using a black-box tool
- Anyone building a private knowledge base for markdown notes
- Engineers preparing for AI, agent, or RAG architecture interviews
- Teams evaluating local RAG before moving to Bedrock, Azure AI Search, Vertex AI, or similar platforms

## Demo

![RAG Knowledge Base demo](docs/images/ScreenCapture.gif)

RAG UI with citation results:

![RAG UI with citation results](docs/images/RAG.png)

## Quick Start

**Pre-requisite**

- Docker Desktop (Compose V2)
- Bash on macOS or Linux, or PowerShell on Windows

Windows (PowerShell, no Bash required):

```powershell
.\scripts\start-local.ps1
```

macOS/Linux (Bash):

```bash
bash scripts/start-local.sh
```

What `start-local` runs under the hood (both Windows and macOS/Linux):

- Starts stack services: `ollama`, `chromadb`, `api`, and `ui`
- Waits for Ollama readiness and ensures required models are available
- Runs one-shot `ingestion` to index markdown content into ChromaDB
- Writes/updates ingestion report (default: `reports/ingestion_report.json`)
- First run can take longer because Docker images and Ollama models are downloaded.

Run ingestion at least once before expecting results in search/answer/UI.

## Access URLs

- RAG UI (Streamlit): `http://localhost:8501/`
- ChromaDB heartbeat: `http://localhost:8000/api/v1/heartbeat`
- Ollama endpoint: `http://localhost:11434/`

## Advanced Startup (Manual Controls)

Use this section when you want to control stack startup and ingestion separately.
For a one-command flow, use `start-local` from Quick Start.

Start only the stack services (`ollama`, `chromadb`, `api`, `ui`):

Windows (PowerShell):

```powershell
.\scripts\start-stack.ps1
```

macOS/Linux (Bash):

```bash
bash scripts/start-stack.sh
```

Run ingestion manually:

Windows (PowerShell):

```powershell
docker compose run --rm --build ingestion
```

macOS/Linux (Bash):

```bash
bash scripts/run-ingestion.sh
```

Default model configuration (from `.env.example`):

- `LLM_MODEL=tinyllama:latest`
- `EMBEDDING_MODEL=nomic-embed-text`

## Configuration

- Use `.env.example` as the reference template (source of truth for config keys/defaults).
- `.env` is your local/internal runtime copy and may vary by machine.
- On first run, scripts auto-create `.env` from `.env.example`.
- If you want to customize values first, copy and edit manually:

```bash
cp .env.example .env
```

- Example override:

```bash
CHROMADB_IMAGE_TAG=0.5.5
```

#### Content source folders:

- Configure domains with `SOURCE_DIRS` in `.env.example`, then copy values to your local `.env`.
- `HOST_KNOWLEDGE_BASE_ROOT` is the host root folder where those domain folders live.

Example with additional folders:

```env
HOST_KNOWLEDGE_BASE_ROOT=../../MyNotes
SOURCE_DIRS=AI,AWS,Interviews,MAWM,MyDocuments
```

With the example above, the ingestion script expects markdown files under:

- `../../MyNotes/AI`
- `../../MyNotes/AWS`
- `../../MyNotes/Interviews`
- `../../MyNotes/MAWM`
- `../../MyNotes/MyDocuments`

## Ingestion Behavior

- `ingestion` is a one-shot pipeline container.
- Output report is written to `reports/ingestion_report.json` by default.
- Incremental mode skips unchanged files based on the previous report timestamp.
- Set `INGESTION_MIN_FILE_DELTA_SECONDS` in `.env.example` (and your local `.env`) to add a re-ingestion buffer for recently modified files.
- Re-ingestion removes old vectors for a source file before writing fresh chunks.

## Verify Services

API Reference:

- Swagger-style document: `docs/api-swagger-style.md`
- Live OpenAPI docs: `http://localhost:8080/docs`

Swagger UI:

![Swagger UI](docs/images/swagger.png)

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

## Run Tests

```bash
/c/Repo/sdontireddy/MyNotes/.venv/Scripts/python -m pytest tests/unit tests/integration/test_ingestion_pipeline.py -q
```

## Stop Stack

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
- Memory constraints forced us to use tinyllama:latest
- Increased timeout, with proper error messaging
