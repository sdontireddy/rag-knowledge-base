"""Embedding service client for Ollama-compatible embedding APIs."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

import httpx


logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates embeddings with retry and backoff for transient failures."""

    def __init__(
        self,
        ollama_base_url: str,
        model: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.25,
        client: httpx.Client | None = None,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._client = client

    def embed(self, text: str) -> list[float]:
        """Embed a single text value."""
        logger.info("embedding_single_started text_length=%s model=%s", len(text or ""), self.model)
        return self._embed_one(text)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed multiple text values in sequence."""
        logger.info("embedding_batch_started batch_size=%s model=%s", len(texts), self.model)
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "embedding_request_attempt attempt=%s max_retries=%s model=%s",
                    attempt,
                    self.max_retries,
                    self.model,
                )
                payload = {"model": self.model, "prompt": text}
                response = self._get_client().post(
                    f"{self.ollama_base_url}/api/embeddings",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Embedding request failed with status {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                response.raise_for_status()
                data = response.json()
                vector = data.get("embedding")
                if not isinstance(vector, list):
                    raise ValueError("Embedding API returned invalid payload: missing embedding vector")
                logger.info(
                    "embedding_request_completed attempt=%s vector_length=%s model=%s",
                    attempt,
                    len(vector),
                    self.model,
                )
                return [float(value) for value in vector]
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "embedding_request_retrying attempt=%s max_retries=%s model=%s",
                    attempt,
                    self.max_retries,
                    self.model,
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))

        logger.error("embedding_request_failed model=%s max_retries=%s", self.model, self.max_retries)
        raise RuntimeError("Embedding request failed after retries") from last_error

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client()
