"""Parser protocol definitions for ingestion."""

from pathlib import Path
from typing import Protocol

from shared.models import Chunk, Document


class DocumentParser(Protocol):
    """Contract implemented by all document parsers."""

    def parse(self, file_path: Path) -> tuple[Document, list[Chunk]]:
        """Parse a source file into a document and chunk list."""
