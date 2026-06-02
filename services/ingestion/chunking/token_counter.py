"""Token counting utilities for chunking decisions."""

import re

try:
    import tiktoken
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    tiktoken = None


class TokenCounter:
    """Counts tokens using a tiktoken encoding."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding = tiktoken.get_encoding(encoding_name) if tiktoken is not None else None

    def count(self, text: str) -> int:
        """Return token count for input text."""
        value = text or ""
        if self._encoding is not None:
            return len(self._encoding.encode(value))

        # Fallback approximation when tiktoken is unavailable.
        return len(re.findall(r"\S+", value))
