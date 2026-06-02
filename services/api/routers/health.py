"""Health and domain endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request

from services.api.models import DomainsResponse, DomainStats, HealthResponse
from services.api.services.vector_store import VectorStoreAdapter

router = APIRouter(prefix="/api", tags=["health"])


def _vector_store(request: Request) -> VectorStoreAdapter | None:
    return getattr(request.app.state, "vector_store", None)


@router.get("/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    services = {"ollama": "down", "chromadb": "down"}

    try:
        response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=2.0)
        if response.is_success:
            services["ollama"] = "up"
    except httpx.HTTPError:
        pass

    vector_store = _vector_store(request)
    vector_count = 0
    if vector_store is not None:
        try:
            vector_count = vector_store.count()
            services["chromadb"] = "up"
        except Exception:
            pass

    status = "healthy" if services["ollama"] == "up" and services["chromadb"] == "up" else "degraded"
    return HealthResponse(
        status=status,
        services={"ollama": services["ollama"], "chromadb": services["chromadb"]},
        vector_store_count=vector_count,
        checked_at=datetime.now(timezone.utc),
    )


@router.get("/domains", response_model=DomainsResponse)
def get_domains(request: Request) -> DomainsResponse:
    vector_store = _vector_store(request)
    if vector_store is None:
        return DomainsResponse(domains=[])

    try:
        stats = vector_store.domain_stats()
    except Exception:
        return DomainsResponse(domains=[])

    domains = [
        DomainStats(
            name=str(item["name"]),
            document_count=int(item["document_count"]),
            chunk_count=int(item["chunk_count"]),
        )
        for item in stats
    ]
    return DomainsResponse(domains=domains)
