"""Parser registry for extension-to-parser resolution."""

from pathlib import Path

from services.ingestion.parsers.base import DocumentParser


class ParserRegistry:
    """Maps file extensions to parser implementations."""

    def __init__(self) -> None:
        self._registry: dict[str, DocumentParser] = {}

    def register(self, extension: str, parser: DocumentParser) -> None:
        normalized = extension.lower().strip()
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        self._registry[normalized] = parser

    def get_parser(self, file_path: Path) -> DocumentParser:
        parser = self._registry.get(file_path.suffix.lower())
        if parser is None:
            raise ValueError(f"No parser registered for extension: {file_path.suffix}")
        return parser
