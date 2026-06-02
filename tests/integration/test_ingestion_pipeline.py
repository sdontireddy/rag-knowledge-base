import os
from datetime import timezone
from pathlib import Path

from services.ingestion.embedding_service import EmbeddingService
from services.ingestion.parsers.markdown_parser import MarkdownParser
from services.ingestion.parsers.registry import ParserRegistry
from services.ingestion.pipeline import IngestionPipeline


class FakeVectorStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def upsert(self, ids, vectors, documents, metadatas) -> None:
        for idx, item_id in enumerate(ids):
            self.rows[item_id] = {
                "vector": vectors[idx],
                "document": documents[idx],
                "metadata": metadatas[idx],
            }

    def query(self, vector, k, where=None):
        return []

    def delete(self, ids) -> None:
        for item_id in ids:
            self.rows.pop(item_id, None)

    def delete_by_source_path(self, source_path: str) -> int:
        ids_to_delete = [item_id for item_id, row in self.rows.items() if row["metadata"]["source_path"] == source_path]
        for item_id in ids_to_delete:
            self.rows.pop(item_id, None)
        return len(ids_to_delete)

    def count(self) -> int:
        return len(self.rows)


class FakeEmbeddingService(EmbeddingService):
    def __init__(self) -> None:
        pass

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]

    def embed_batch(self, texts):
        return [self.embed(text) for text in texts]


def test_ingestion_pipeline_idempotence_and_report_invariant(tmp_path: Path) -> None:
    kb_root = tmp_path / "knowledge_base"
    source = kb_root / "AWS"
    source.mkdir(parents=True, exist_ok=True)

    (source / "Bedrock.md").write_text("# Bedrock\n\ncontent one", encoding="utf-8")
    (source / "CloudFront.md").write_text("# CloudFront\n\ncontent two", encoding="utf-8")

    registry = ParserRegistry()
    registry.register(".md", MarkdownParser(max_tokens=50, min_tokens=5))

    store = FakeVectorStore()
    pipeline = IngestionPipeline(
        parser_registry=registry,
        embedding_service=FakeEmbeddingService(),
        vector_store=store,
        knowledge_base_root=kb_root,
        source_dirs=["AWS"],
    )

    report_first = pipeline.run()
    report_second = IngestionPipeline(
        parser_registry=registry,
        embedding_service=FakeEmbeddingService(),
        vector_store=store,
        knowledge_base_root=kb_root,
        source_dirs=["AWS"],
        last_successful_run_at=report_first.completed_at,
    ).run()

    assert report_first.total_files_discovered == 2
    assert report_first.total_files_ingested == 2
    assert report_first.skipped_duplicates == 0
    assert report_first.skipped_unchanged == 0
    assert report_first.total_chunks_created == report_first.total_embeddings_stored
    assert (
        report_first.total_files_ingested
        + report_first.skipped_duplicates
        + report_first.skipped_unchanged
        + len(report_first.errors)
        == report_first.total_files_discovered
    )

    assert report_second.total_files_discovered == 2
    assert report_second.total_files_ingested == 0
    assert report_second.skipped_duplicates == 0
    assert report_second.skipped_unchanged == 2
    assert store.count() == report_first.total_chunks_created

    cloudfront = source / "CloudFront.md"
    cloudfront.write_text("# CloudFront\n\ncontent two updated", encoding="utf-8")
    future_timestamp = report_second.completed_at.timestamp() + 2
    os.utime(cloudfront, (future_timestamp, future_timestamp))

    report_third = IngestionPipeline(
        parser_registry=registry,
        embedding_service=FakeEmbeddingService(),
        vector_store=store,
        knowledge_base_root=kb_root,
        source_dirs=["AWS"],
        last_successful_run_at=report_second.completed_at.astimezone(timezone.utc),
        min_file_delta_seconds=0,
    ).run()

    assert report_third.total_files_discovered == 2
    assert report_third.total_files_ingested == 1
    assert report_third.skipped_unchanged == 1
    assert report_third.skipped_duplicates == 0
