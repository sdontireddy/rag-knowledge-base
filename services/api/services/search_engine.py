"""Search engine implementation for semantic retrieval."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from services.api.services.vector_store import VectorStoreAdapter
from services.ingestion.embedding_service import EmbeddingService


class SearchEngine:
    """Performs embedding-based similarity search over vector store chunks."""

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStoreAdapter) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        k: int,
        domain_filter: Sequence[str] | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        query_vector = self.embedding_service.embed(query)
        query_terms = self._tokenize(query)

        where = None
        if domain_filter and len(domain_filter) == 1:
            where = {"domain": domain_filter[0]}

        candidate_k = max(k * 4, 20)
        raw_results = self.vector_store.query(vector=query_vector, k=candidate_k, where=where)
        normalized = self._normalize_results(raw_results)

        allowed = set(domain_filter or [])
        filtered: list[dict[str, Any]] = []
        for item in normalized:
            if allowed and item["domain"] not in allowed:
                continue
            if item["relevance_score"] < min_score:
                continue
            filtered.append(item)

        for item in filtered:
            item["rank_score"] = item["relevance_score"] + 1.0 * self._keyword_overlap_score(query_terms, item)

        filtered.sort(key=lambda item: item["rank_score"], reverse=True)
        for index, item in enumerate(filtered, start=1):
            item["rank"] = index

        return filtered[:k]

    def _normalize_results(self, raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in raw_results:
            metadata = item.get("metadata", {}) or {}
            distance = item.get("distance")
            relevance_score = self._distance_to_relevance(distance)

            heading = metadata.get("heading_hierarchy") or ""
            if isinstance(heading, list):
                section = " > ".join(str(part) for part in heading)
            else:
                section = str(heading)

            normalized.append(
                {
                    "chunk_id": str(item.get("id", "")),
                    "text": str(item.get("document", "")),
                    "source_path": str(metadata.get("source_path", "")),
                    "domain": str(metadata.get("domain", "unknown")),
                    "section": section,
                    "relevance_score": relevance_score,
                }
            )
        return normalized

    def _distance_to_relevance(self, distance: Any) -> float:
        if distance is None:
            return 0.0
        try:
            value = float(distance)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(1.0, 1.0 / (1.0 + value)))

    def _keyword_overlap_score(self, query_terms: set[str], item: dict[str, Any]) -> float:
        if not query_terms:
            return 0.0

        corpus = " ".join(
            [
                str(item.get("text", "")),
                str(item.get("source_path", "")),
                str(item.get("section", "")),
                str(item.get("domain", "")),
            ]
        )
        doc_terms = self._tokenize(corpus)
        if not doc_terms:
            return 0.0

        overlap = len(query_terms & doc_terms)
        return overlap / max(1, len(query_terms))

    def _tokenize(self, text: str) -> set[str]:
        if not text:
            return set()

        expanded = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        tokens = re.findall(r"[a-zA-Z0-9]{3,}", expanded.lower())
        return set(tokens)
