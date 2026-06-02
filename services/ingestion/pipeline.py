"""Ingestion pipeline orchestration."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.ingestion.embedding_service import EmbeddingService
from services.ingestion.parsers.registry import ParserRegistry
from shared.models import IngestionReport


logger = logging.getLogger(__name__)


class IngestionPipeline:
	"""Coordinates file discovery, parsing, embedding, and vector storage."""

	def __init__(
		self,
		parser_registry: ParserRegistry,
		embedding_service: EmbeddingService,
		vector_store: Any,
		knowledge_base_root: Path,
		source_dirs: list[str],
		last_successful_run_at: datetime | None = None,
		min_file_delta_seconds: int = 0,
	) -> None:
		self.parser_registry = parser_registry
		self.embedding_service = embedding_service
		self.vector_store = vector_store
		self.knowledge_base_root = knowledge_base_root
		self.source_dirs = source_dirs
		self.last_successful_run_at = last_successful_run_at
		self.min_file_delta_seconds = min_file_delta_seconds

	def run(self) -> IngestionReport:
		"""Run a full ingestion cycle and return report metrics."""
		started_at = datetime.now(timezone.utc)
		discovered = self._discover_files()
		logger.info(
			"ingestion_run_started total_files_discovered=%s source_dirs=%s",
			len(discovered),
			self.source_dirs,
		)

		ingested = 0
		skipped_duplicates = 0
		skipped_unchanged = 0
		total_chunks_created = 0
		total_embeddings_stored = 0
		errors: list[dict[str, str]] = []
		domains_covered: set[str] = set()
		seen_hashes: set[str] = set()

		for file_path in discovered:
			try:
				if self._is_unchanged_since_last_run(file_path):
					skipped_unchanged += 1
					logger.info(
						"ingestion_unchanged_skipped file_path=%s modified_at=%s baseline=%s min_delta_seconds=%s",
						file_path.as_posix(),
						self._file_modified_at(file_path).isoformat(),
						self.last_successful_run_at.isoformat() if self.last_successful_run_at is not None else None,
						self.min_file_delta_seconds,
					)
					continue

				logger.info("ingestion_file_started file_path=%s", file_path.as_posix())
				parser = self.parser_registry.get_parser(file_path)
				document, chunks = parser.parse(file_path)

				content_hash = self._compute_content_hash(file_path)
				if self._is_duplicate(content_hash, seen_hashes):
					skipped_duplicates += 1
					logger.info(
						"ingestion_duplicate_skipped file_path=%s content_hash=%s",
						file_path.as_posix(),
						content_hash,
					)
					continue

				deleted_vectors = self.vector_store.delete_by_source_path(document.source_path)
				if deleted_vectors:
					logger.info(
						"ingestion_existing_vectors_deleted file_path=%s source_path=%s deleted_vectors=%s",
						file_path.as_posix(),
						document.source_path,
						deleted_vectors,
					)

				if not chunks:
					ingested += 1
					domains_covered.add(document.domain)
					logger.info(
						"ingestion_file_no_chunks file_path=%s domain=%s",
						file_path.as_posix(),
						document.domain,
					)
					continue

				logger.info(
					"ingestion_embedding_started file_path=%s chunk_count=%s domain=%s",
					file_path.as_posix(),
					len(chunks),
					document.domain,
				)
				vectors = self.embedding_service.embed_batch([chunk.text for chunk in chunks])
				metadatas = [
					{
						"chunk_id": chunk.id,
						"document_id": chunk.document_id,
						"domain": chunk.domain,
						"source_path": chunk.source_path,
						"heading_hierarchy": " > ".join(chunk.heading_hierarchy),
						"chunk_type": chunk.chunk_type,
						"chunk_index": chunk.chunk_index,
						"token_count": chunk.token_count,
						"content_hash": document.content_hash,
					}
					for chunk in chunks
				]

				self.vector_store.upsert(
					ids=[chunk.id for chunk in chunks],
					vectors=vectors,
					documents=[chunk.text for chunk in chunks],
					metadatas=metadatas,
				)

				ingested += 1
				total_chunks_created += len(chunks)
				total_embeddings_stored += len(vectors)
				domains_covered.add(document.domain)
				logger.info(
					"ingestion_file_completed file_path=%s chunk_count=%s embedding_count=%s domain=%s",
					file_path.as_posix(),
					len(chunks),
					len(vectors),
					document.domain,
				)
			except Exception as exc:  # pragma: no cover - tested via integration behavior
				errors.append(
					{
						"file_path": str(file_path.as_posix()),
						"error_message": str(exc),
					}
				)
				logger.exception(
					"ingestion_file_failed file_path=%s error_message=%s",
					file_path.as_posix(),
					str(exc),
				)

		completed_at = datetime.now(timezone.utc)
		report = IngestionReport(
			started_at=started_at,
			completed_at=completed_at,
			incremental_baseline_at=self.last_successful_run_at,
			total_files_discovered=len(discovered),
			total_files_ingested=ingested,
			total_chunks_created=total_chunks_created,
			total_embeddings_stored=total_embeddings_stored,
			skipped_duplicates=skipped_duplicates,
			skipped_unchanged=skipped_unchanged,
			errors=errors,
			domains_covered=sorted(domains_covered),
		)

		invariant = (
			report.total_files_ingested
			+ report.skipped_duplicates
			+ report.skipped_unchanged
			+ len(report.errors)
		)
		if invariant != report.total_files_discovered:
			raise RuntimeError("Ingestion report invariant violated")

		logger.info(
			"ingestion_run_completed files_discovered=%s files_ingested=%s chunks=%s embeddings=%s duplicates=%s unchanged=%s errors=%s",
			report.total_files_discovered,
			report.total_files_ingested,
			report.total_chunks_created,
			report.total_embeddings_stored,
			report.skipped_duplicates,
			report.skipped_unchanged,
			len(report.errors),
		)

		return report

	def _discover_files(self) -> list[Path]:
		files: list[Path] = []
		for source in self.source_dirs:
			source_root = self.knowledge_base_root / source
			if not source_root.exists():
				continue
			files.extend(path for path in source_root.rglob("*.md") if path.is_file())
		files.sort()
		return files

	def _compute_content_hash(self, file_path: Path) -> str:
		data = file_path.read_bytes()
		return hashlib.sha256(data).hexdigest()

	def _is_duplicate(self, content_hash: str, seen_hashes: set[str]) -> bool:
		if content_hash in seen_hashes:
			return True
		seen_hashes.add(content_hash)
		return False

	def _file_modified_at(self, file_path: Path) -> datetime:
		return datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)

	def _is_unchanged_since_last_run(self, file_path: Path) -> bool:
		if self.last_successful_run_at is None:
			return False

		cutoff = self.last_successful_run_at + timedelta(seconds=self.min_file_delta_seconds)
		return self._file_modified_at(file_path) <= cutoff
