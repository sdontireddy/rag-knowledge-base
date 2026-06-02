"""Shared data models for ingestion, search, and answer workflows."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Document:
    """Represents a source markdown document."""

    id: str
    source_path: str
    domain: str
    title: str
    content: str
    content_hash: str
    created_at: datetime
    modified_at: datetime
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """Represents a token-bounded chunk derived from a document."""

    id: str
    document_id: str
    domain: str
    source_path: str
    text: str
    token_count: int
    chunk_index: int
    heading_hierarchy: list[str]
    chunk_type: str
    language: Optional[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Embedding:
    """Stores an embedding vector for a chunk."""

    chunk_id: str
    vector: list[float]
    model: str
    created_at: datetime


@dataclass
class SearchResult:
    """A ranked search match with relevance score."""

    chunk: Chunk
    relevance_score: float
    rank: int


@dataclass
class Citation:
    """Citation metadata used in generated answers."""

    chunk_id: str
    source_path: str
    domain: str
    section: str
    relevance_score: float


@dataclass
class Answer:
    """Generated answer and its retrieval context."""

    query: str
    answer_text: str
    citations: list[Citation]
    model: str
    context_chunks: list[SearchResult]
    generated_at: datetime
    generation_time_ms: int


@dataclass
class IngestionReport:
    """Summary of an ingestion run."""

    started_at: datetime
    completed_at: datetime
    incremental_baseline_at: Optional[datetime]
    total_files_discovered: int
    total_files_ingested: int
    total_chunks_created: int
    total_embeddings_stored: int
    skipped_duplicates: int
    skipped_unchanged: int
    errors: list[dict[str, Any]]
    domains_covered: list[str]
