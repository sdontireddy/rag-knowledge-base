"""Local wrapper API exposing simplified RAG endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.ui.local_rag_client import LocalRagApiError, LocalRagClient


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=25)
    domain_filter: list[str] | None = None
    max_tokens: int = Field(default=1024, ge=64, le=4096)


app = FastAPI(title="Local RAG Wrapper API")
rag_client = LocalRagClient()


@app.get("/health")
def health() -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        upstream = rag_client.health()
    except LocalRagApiError as exc:
        return {
            "status": "degraded",
            "upstream": "down",
            "checked_at": checked_at,
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "upstream": "up",
        "checked_at": checked_at,
        "upstream_health": upstream,
    }


@app.get(
    "/domains",
    responses={502: {"description": "Upstream RAG API request failed"}},
)
def domains() -> dict:
    try:
        names = rag_client.domains()
    except LocalRagApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "domains": [
            {
                "name": name,
                "document_count": 0,
                "chunk_count": 0,
            }
            for name in names
        ]
    }


@app.post(
    "/ask",
    responses={502: {"description": "Upstream RAG API request failed"}},
)
@app.post(
    "/api/answer",
    responses={502: {"description": "Upstream RAG API request failed"}},
)
def ask(payload: AskRequest) -> dict:
    try:
        return rag_client.ask(
            query=payload.query,
            domain_filter=payload.domain_filter,
            k=payload.k,
            max_tokens=payload.max_tokens,
        )
    except LocalRagApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
