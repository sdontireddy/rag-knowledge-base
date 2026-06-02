"""Vector store abstractions and ChromaDB-backed implementation."""

from __future__ import annotations

from typing import Any, Protocol

try:
    import chromadb
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    chromadb = None


class VectorStoreAdapter(Protocol):
    """Minimal protocol for vector storage and retrieval."""

    def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert or update vectors and associated metadata."""

    def query(self, vector: list[float], k: int, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Query nearest vectors and return normalized result list."""

    def delete(self, ids: list[str]) -> None:
        """Delete vectors by ID."""

    def delete_by_source_path(self, source_path: str) -> int:
        """Delete all vectors associated with a source file and return deleted count."""

    def count(self) -> int:
        """Return number of stored vectors."""

    def domain_stats(self) -> list[dict[str, int | str]]:
        """Return aggregated domain statistics."""


class ChromaVectorStore:
    """ChromaDB adapter used by API and ingestion services."""

    def __init__(
        self,
        host: str,
        port: int,
        collection_name: str,
        collection: Any | None = None,
    ) -> None:
        self.collection_name = collection_name
        if collection is not None:
            self._collection = collection
            return

        if chromadb is None:
            raise RuntimeError("chromadb is required to instantiate ChromaVectorStore without a prebuilt collection")

        client = chromadb.HttpClient(host=host, port=port)
        self._collection = client.get_or_create_collection(name=collection_name)

    def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self._collection.upsert(ids=ids, embeddings=vectors, documents=documents, metadatas=metadatas)

    def query(self, vector: list[float], k: int, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "query_embeddings": [vector],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)
        ids = raw.get("ids", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        results: list[dict[str, Any]] = []
        for idx, item_id in enumerate(ids):
            results.append(
                {
                    "id": item_id,
                    "document": documents[idx] if idx < len(documents) else "",
                    "metadata": metadatas[idx] if idx < len(metadatas) else {},
                    "distance": distances[idx] if idx < len(distances) else None,
                }
            )
        return results

    def delete(self, ids: list[str]) -> None:
        self._collection.delete(ids=ids)

    def delete_by_source_path(self, source_path: str) -> int:
        raw = self._collection.get(where={"source_path": source_path})
        ids = raw.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return int(self._collection.count())

    def domain_stats(self) -> list[dict[str, int | str]]:
        raw = self._collection.get(include=["metadatas"])
        metadatas = raw.get("metadatas", [])

        chunk_counts: dict[str, int] = {}
        doc_sets: dict[str, set[str]] = {}

        for metadata in metadatas:
            domain = str((metadata or {}).get("domain", "unknown"))
            chunk_counts[domain] = chunk_counts.get(domain, 0) + 1

            document_id = str((metadata or {}).get("document_id", ""))
            if domain not in doc_sets:
                doc_sets[domain] = set()
            if document_id:
                doc_sets[domain].add(document_id)

        stats: list[dict[str, int | str]] = []
        for domain, chunk_count in sorted(chunk_counts.items()):
            stats.append(
                {
                    "name": domain,
                    "document_count": len(doc_sets.get(domain, set())),
                    "chunk_count": chunk_count,
                }
            )
        return stats
