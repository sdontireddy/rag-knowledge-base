"""Pydantic models for API request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=25)
    domain_filter: list[str] | None = None
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchResultModel(BaseModel):
    chunk_id: str
    text: str
    source_path: str
    domain: str
    section: str
    relevance_score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultModel]


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=25)
    domain_filter: list[str] | None = None
    max_tokens: int = Field(default=1024, ge=64, le=4096)


class CitationModel(BaseModel):
    chunk_id: str
    source_path: str
    domain: str
    section: str
    relevance_score: float


class AnswerResponse(BaseModel):
    query: str
    answer_text: str
    citations: list[CitationModel]
    context_chunks: list[SearchResultModel]
    model: str
    generation_time_ms: int


class IngestRequest(BaseModel):
    source_dirs: list[str] | None = None
    full_reindex: bool = False
    dry_run: bool = False
    priority: Literal["low", "normal", "high"] = "normal"
    metadata_overrides: dict[str, Any] = Field(default_factory=dict)


class IngestStartResponse(BaseModel):
    status: Literal["started"]
    job_id: str


class IngestProgress(BaseModel):
    files_processed: int = 0
    total_files_discovered: int = 0


class IngestStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: IngestProgress
    request_effective: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] | None = None
    error_summary: dict[str, Any] | None = None


class DomainStats(BaseModel):
    name: str
    document_count: int
    chunk_count: int


class DomainsResponse(BaseModel):
    domains: list[DomainStats]


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    services: dict[str, Literal["up", "down"]]
    vector_store_count: int
    checked_at: datetime
