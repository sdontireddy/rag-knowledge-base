"""Answer generation constrained to retrieved vector-store context."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from typing import Any

import httpx

from services.api.services.answer_prompt import build_strict_rag_prompt


logger = logging.getLogger(__name__)

_RESPONSE_PATTERN = re.compile(r"ANSWER:\s*(.*?)\s*CITATIONS:\s*(.*)\Z", re.DOTALL)
_INLINE_CITATION_PATTERN = re.compile(r"\[([^\]]+)\]")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]{3,}")
_QUERY_STOPWORDS = {
    "give",
    "show",
    "tell",
    "details",
    "detail",
    "about",
    "what",
    "where",
    "when",
    "how",
    "please",
    "need",
    "want",
    "me",
}


class AnswerGenerator:
    """Builds a strict RAG prompt, calls Ollama, and validates citations."""

    def __init__(
        self,
        ollama_base_url: str,
        model: str,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client

    def generate(self, query: str, context_chunks: Sequence[dict[str, Any]], max_tokens: int = 1024) -> dict[str, Any]:
        started = time.perf_counter()
        if not context_chunks:
            return {
                "answer_text": "INSUFFICIENT_CONTEXT",
                "citations": [],
                "context_chunks": [],
                "model": self.model,
                "generation_time_ms": self._elapsed_ms(started),
            }

        prompt = build_strict_rag_prompt(query=query, context_chunks=context_chunks)
        try:
            raw_text = self._generate_text(prompt=prompt, max_tokens=max_tokens)
        except RuntimeError:
            raw_text = "ANSWER:\nINSUFFICIENT_CONTEXT\nCITATIONS:\nNONE"
        answer_text, citation_ids = self._normalize_output(raw_text=raw_text, context_chunks=context_chunks)
        if answer_text == "INSUFFICIENT_CONTEXT":
            fallback_answer, fallback_ids = self._build_extractive_fallback(query=query, context_chunks=context_chunks)
            if fallback_answer is not None and fallback_ids:
                answer_text, citation_ids = fallback_answer, fallback_ids
        citations = self._resolve_citations(citation_ids=citation_ids, context_chunks=context_chunks)

        return {
            "answer_text": answer_text,
            "citations": citations,
            "context_chunks": [dict(chunk) for chunk in context_chunks],
            "model": self.model,
            "generation_time_ms": self._elapsed_ms(started),
        }

    def _generate_text(self, prompt: str, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": max_tokens,
            },
        }
        try:
            response = self._get_client().post(
                f"{self.ollama_base_url}/api/generate",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - runtime network behavior
            logger.warning("answer_generation_failed model=%s error=%s", self.model, exc)
            raise RuntimeError("Answer generation failed") from exc

        body = response.json()
        text = body.get("response")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Answer generation returned an empty response")
        return text.strip()

    def _normalize_output(self, raw_text: str, context_chunks: Sequence[dict[str, Any]]) -> tuple[str, list[str]]:
        valid_ids = {str(chunk.get("chunk_id", "")) for chunk in context_chunks}
        match = _RESPONSE_PATTERN.search(raw_text.strip())
        if match is None:
            return "INSUFFICIENT_CONTEXT", []

        answer_body = match.group(1).strip()
        citations_block = match.group(2).strip()

        if answer_body == "INSUFFICIENT_CONTEXT":
            return "INSUFFICIENT_CONTEXT", []

        inline_ids = [item.strip() for item in _INLINE_CITATION_PATTERN.findall(answer_body) if item.strip()]
        if not inline_ids or any(item not in valid_ids for item in inline_ids):
            return "INSUFFICIENT_CONTEXT", []

        if not self._has_sentence_level_citations(answer_body=answer_body, valid_ids=valid_ids):
            return "INSUFFICIENT_CONTEXT", []

        citation_ids = [item.strip() for item in citations_block.split(",") if item.strip() and item.strip() != "NONE"]
        filtered_ids = [item for item in citation_ids if item in valid_ids]
        if not filtered_ids:
            filtered_ids = [item for item in inline_ids if item in valid_ids]

        if not filtered_ids:
            return "INSUFFICIENT_CONTEXT", []

        ordered_unique_ids: list[str] = []
        for item in filtered_ids:
            if item not in ordered_unique_ids:
                ordered_unique_ids.append(item)

        return answer_body, ordered_unique_ids

    def _has_sentence_level_citations(self, answer_body: str, valid_ids: set[str]) -> bool:
        segments = [segment.strip() for segment in _SENTENCE_SPLIT_PATTERN.split(answer_body) if segment.strip()]
        if not segments:
            return False

        for segment in segments:
            if not any(ch.isalnum() for ch in segment):
                continue
            segment_ids = [item.strip() for item in _INLINE_CITATION_PATTERN.findall(segment) if item.strip()]
            if not segment_ids:
                return False
            if any(item not in valid_ids for item in segment_ids):
                return False

        return True

    def _build_extractive_fallback(
        self,
        query: str,
        context_chunks: Sequence[dict[str, Any]],
    ) -> tuple[str | None, list[str]]:
        query_terms = {token for token in _TOKEN_PATTERN.findall(query.lower()) if token not in _QUERY_STOPWORDS}
        if not query_terms:
            return None, []

        candidates: list[tuple[str, str, float, float]] = []
        for chunk in context_chunks[:5]:
            chunk_id = str(chunk.get("chunk_id", "")).strip()
            text = str(chunk.get("text", "")).strip()
            source_path = str(chunk.get("source_path", "")).strip()
            section = str(chunk.get("section", "")).strip()
            if not chunk_id or not text:
                continue

            corpus = " ".join(part for part in [text, source_path, section] if part)
            text_terms = set(_TOKEN_PATTERN.findall(corpus.lower()))
            overlap_terms = query_terms & text_terms
            if not overlap_terms:
                continue

            score = float(chunk.get("relevance_score", 0.0) or 0.0)
            lexical = len(overlap_terms) / max(1, len(query_terms))
            sentence = self._first_sentence(text)
            if sentence:
                candidates.append((chunk_id, sentence, score, lexical))

        if not candidates:
            return None, []

        candidates.sort(key=lambda item: (item[3], item[2]), reverse=True)
        selected = candidates[:2]

        parts: list[str] = []
        used_ids: list[str] = []
        for chunk_id, sentence, _, _ in selected:
            parts.append(f"{sentence} [{chunk_id}]")
            used_ids.append(chunk_id)

        if not parts:
            return None, []

        answer = " ".join(parts)
        return answer, used_ids

    def _first_sentence(self, text: str) -> str:
        compact = " ".join(text.split())
        if not compact:
            return ""

        pieces = [piece.strip() for piece in _SENTENCE_SPLIT_PATTERN.split(compact) if piece.strip()]
        first = pieces[0] if pieces else compact
        return first[:260]

    def _resolve_citations(
        self,
        citation_ids: Sequence[str],
        context_chunks: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        chunk_lookup = {str(chunk.get("chunk_id", "")): dict(chunk) for chunk in context_chunks}
        return [chunk_lookup[item] for item in citation_ids if item in chunk_lookup]

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client()