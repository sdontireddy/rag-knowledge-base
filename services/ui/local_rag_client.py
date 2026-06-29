"""Reusable client for local RAG API and wrapper API endpoints."""

from __future__ import annotations

import os
from typing import Any

import httpx


class LocalRagApiError(RuntimeError):
    """Raised when calls to the RAG API fail."""


class LocalRagClient:
    """Thin wrapper around local RAG API endpoints used by UI and agents."""

    def __init__(
        self,
        base_url: str | None = None,
        answer_timeout_seconds: float | None = None,
    ) -> None:
        resolved_base_url = (base_url or os.getenv("API_BASE_URL", "http://api:8080")).rstrip("/")
        timeout_value = answer_timeout_seconds
        if timeout_value is None:
            timeout_value = float(os.getenv("UI_ANSWER_TIMEOUT_SECONDS", "90"))

        self.base_url = resolved_base_url
        self.answer_timeout_seconds = timeout_value

    def _request(
        self,
        method: str,
        endpoint_candidates: list[str],
        *,
        json: dict[str, Any] | None = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> httpx.Response:
        if timeout is None:
            timeout = 5.0

        last_error: Exception | None = None
        for endpoint in endpoint_candidates:
            try:
                response = httpx.request(
                    method,
                    f"{self.base_url}{endpoint}",
                    json=json,
                    timeout=timeout,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                continue

            if response.status_code == 404:
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise LocalRagApiError(f"{method} {endpoint} failed: {exc}") from exc

            return response

        if last_error is not None:
            raise LocalRagApiError(f"{method} request failed: {last_error}") from last_error

        raise LocalRagApiError(
            f"No compatible endpoint found for {method}: {', '.join(endpoint_candidates)}"
        )

    def ask(
        self,
        *,
        query: str,
        domain_filter: list[str] | None,
        k: int,
        max_tokens: int,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            ["/ask", "/api/answer"],
            json={
                "query": query,
                "domain_filter": domain_filter or None,
                "k": k,
                "max_tokens": max_tokens,
            },
            timeout=httpx.Timeout(timeout=self.answer_timeout_seconds, connect=5.0),
        )
        return response.json()

    def domains(self) -> list[str]:
        response = self._request("GET", ["/domains", "/api/domains"], timeout=5.0)
        payload = response.json()
        return [str(item.get("name", "")) for item in payload.get("domains", []) if item.get("name")]

    def health(self) -> dict[str, Any]:
        response = self._request("GET", ["/health", "/api/health", "/healthz"], timeout=5.0)
        return response.json()
