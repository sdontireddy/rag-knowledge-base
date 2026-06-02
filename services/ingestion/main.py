"""Ingestion service entrypoint."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from services.api.services.vector_store import ChromaVectorStore
from services.ingestion.config import IngestionSettings
from services.ingestion.embedding_service import EmbeddingService
from services.ingestion.parsers.markdown_parser import MarkdownParser
from services.ingestion.parsers.registry import ParserRegistry
from services.ingestion.pipeline import IngestionPipeline
from shared.models import IngestionReport


def _serialize_report(report: IngestionReport) -> dict[str, object]:
    return {
        "started_at": report.started_at.isoformat(),
        "completed_at": report.completed_at.isoformat(),
        "incremental_baseline_at": report.incremental_baseline_at.isoformat()
        if report.incremental_baseline_at is not None
        else None,
        "total_files_discovered": report.total_files_discovered,
        "total_files_ingested": report.total_files_ingested,
        "total_chunks_created": report.total_chunks_created,
        "total_embeddings_stored": report.total_embeddings_stored,
        "skipped_duplicates": report.skipped_duplicates,
        "skipped_unchanged": report.skipped_unchanged,
        "errors": report.errors,
        "domains_covered": report.domains_covered,
    }


def _load_previous_completed_at(report_path: Path) -> datetime | None:
    if not report_path.exists():
        return None

    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None

    completed_at = raw.get("completed_at")
    if not isinstance(completed_at, str) or not completed_at:
        return None

    try:
        return datetime.fromisoformat(completed_at)
    except ValueError:
        return None


def main() -> None:
    settings = IngestionSettings()
    report_path = Path(settings.ingestion_report_path)
    previous_completed_at = _load_previous_completed_at(report_path)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)
    logger.info(
        "ingestion_start knowledge_base_root=%s source_dirs=%s chroma_collection=%s incremental_baseline_at=%s min_file_delta_seconds=%s",
        settings.knowledge_base_root,
        settings.source_dir_list,
        settings.chroma_collection,
        previous_completed_at.isoformat() if previous_completed_at is not None else None,
        settings.ingestion_min_file_delta_seconds,
    )

    registry = ParserRegistry()
    registry.register(
        ".md",
        MarkdownParser(
            max_tokens=settings.max_chunk_tokens,
            min_tokens=settings.min_chunk_tokens,
        ),
    )

    embedding_service = EmbeddingService(
        ollama_base_url=settings.ollama_base_url,
        model=settings.embedding_model,
    )
    vector_store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=settings.chroma_collection,
    )

    pipeline = IngestionPipeline(
        parser_registry=registry,
        embedding_service=embedding_service,
        vector_store=vector_store,
        knowledge_base_root=Path(settings.knowledge_base_root),
        source_dirs=settings.source_dir_list,
        last_successful_run_at=previous_completed_at,
        min_file_delta_seconds=settings.ingestion_min_file_delta_seconds,
    )
    report = pipeline.run()

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(_serialize_report(report), indent=2), encoding="utf-8")
    logger.info(
        "ingestion_complete report_path=%s files_discovered=%s files_ingested=%s chunks=%s duplicates=%s unchanged=%s errors=%s",
        report_path,
        report.total_files_discovered,
        report.total_files_ingested,
        report.total_chunks_created,
        report.skipped_duplicates,
        report.skipped_unchanged,
        len(report.errors),
    )
    print(f"Ingestion completed. Report written to {report_path}")


if __name__ == "__main__":
    main()
