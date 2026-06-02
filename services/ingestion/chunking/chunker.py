"""Text chunking utilities used by parsers."""

import logging

from services.ingestion.chunking.token_counter import TokenCounter


logger = logging.getLogger(__name__)


class TextChunker:
    """Split and merge paragraph chunks using token constraints."""

    def __init__(
        self,
        max_tokens: int = 1000,
        min_tokens: int = 100,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.token_counter = token_counter or TokenCounter()

    def split_paragraphs(self, text: str) -> list[str]:
        """Split text into chunks that do not exceed max_tokens."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return []

        logger.debug("chunk_split_started paragraph_count=%s max_tokens=%s", len(paragraphs), self.max_tokens)

        chunks: list[str] = []
        current: list[str] = []
        for para in paragraphs:
            candidate = "\n\n".join(current + [para])
            if current and self.token_counter.count(candidate) > self.max_tokens:
                chunks.append("\n\n".join(current))
                current = [para]
            else:
                current.append(para)

        if current:
            chunks.append("\n\n".join(current))

        logger.debug("chunk_split_completed chunk_count=%s max_tokens=%s", len(chunks), self.max_tokens)

        return chunks

    def merge_small(self, chunks: list[str]) -> list[str]:
        """Merge adjacent chunks smaller than min_tokens."""
        if not chunks:
            return []

        logger.debug(
            "chunk_merge_started chunk_count=%s min_tokens=%s max_tokens=%s",
            len(chunks),
            self.min_tokens,
            self.max_tokens,
        )

        merged: list[str] = []
        idx = 0
        while idx < len(chunks):
            current = chunks[idx]
            current_tokens = self.token_counter.count(current)
            if current_tokens >= self.min_tokens or idx + 1 >= len(chunks):
                merged.append(current)
                idx += 1
                continue

            combined = f"{current}\n\n{chunks[idx + 1]}"
            if self.token_counter.count(combined) <= self.max_tokens:
                merged.append(combined)
                idx += 2
            else:
                merged.append(current)
                idx += 1

            logger.debug("chunk_merge_completed merged_count=%s min_tokens=%s", len(merged), self.min_tokens)

        return merged
