"""FastAPI service entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.api.config import Settings
from services.api.routers.health import router as health_router
from services.api.routers.search import router as search_router
from services.api.services.answer_generator import AnswerGenerator
from services.api.services.search_engine import SearchEngine
from services.api.services.vector_store import ChromaVectorStore
from services.ingestion.embedding_service import EmbeddingService


def _build_vector_store(settings: Settings) -> ChromaVectorStore | None:
    try:
        return ChromaVectorStore(
            host=settings.chroma_host,
            port=settings.chroma_port,
            collection_name=settings.chroma_collection,
        )
    except Exception as exc:  # pragma: no cover - runtime dependency/network conditions
        logging.getLogger(__name__).warning("Vector store unavailable during startup: %s", exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    app.state.settings = settings
    vector_store = _build_vector_store(settings)
    app.state.vector_store = vector_store

    if vector_store is not None:
        embedding_service = EmbeddingService(
            ollama_base_url=settings.ollama_base_url,
            model=settings.embedding_model,
        )
        app.state.search_engine = SearchEngine(
            embedding_service=embedding_service,
            vector_store=vector_store,
        )
        app.state.answer_generator = AnswerGenerator(
            ollama_base_url=settings.ollama_base_url,
            model=settings.llm_model,
            timeout_seconds=float(settings.answer_timeout_seconds),
        )
    else:
        app.state.search_engine = None
        app.state.answer_generator = None
    yield


app = FastAPI(title="RAG Knowledge Base API", lifespan=lifespan)
app.include_router(health_router)
app.include_router(search_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
