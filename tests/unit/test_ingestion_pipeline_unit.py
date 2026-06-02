from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.ingestion.parsers.markdown_parser import MarkdownParser
from services.ingestion.parsers.registry import ParserRegistry
from services.ingestion.pipeline import IngestionPipeline


class FakeEmbeddingService:
    def embed_batch(self, texts):
        return [[float(len(text)), 0.0] for text in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.rows = {}

    def upsert(self, ids, vectors, documents, metadatas) -> None:
        for idx, item_id in enumerate(ids):
            self.rows[item_id] = {
                "vector": vectors[idx],
                "document": documents[idx],
                "metadata": metadatas[idx],
            }

    def delete_by_source_path(self, source_path: str) -> int:
        ids_to_delete = [item_id for item_id, row in self.rows.items() if row["metadata"]["source_path"] == source_path]
        for item_id in ids_to_delete:
            self.rows.pop(item_id, None)
        return len(ids_to_delete)


def test_pipeline_discovers_files_and_writes_vectors(tmp_path: Path) -> None:
    kb_root = tmp_path / "knowledge_base"
    source = kb_root / "AWS"
    source.mkdir(parents=True)
    (source / "a.md").write_text("# A\n\ntext one", encoding="utf-8")
    (source / "b.md").write_text("# B\n\ntext two", encoding="utf-8")

    registry = ParserRegistry()
    registry.register(".md", MarkdownParser(max_tokens=50, min_tokens=5))

    vector_store = FakeVectorStore()
    pipeline = IngestionPipeline(
        parser_registry=registry,
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        knowledge_base_root=kb_root,
        source_dirs=["AWS"],
    )

    report = pipeline.run()

    assert report.total_files_discovered == 2
    assert report.total_files_ingested == 2
    assert report.skipped_duplicates == 0
    assert report.skipped_unchanged == 0
    assert report.total_chunks_created == report.total_embeddings_stored
    assert len(vector_store.rows) == report.total_chunks_created


def test_pipeline_skips_files_unchanged_since_last_successful_run(tmp_path: Path) -> None:
    kb_root = tmp_path / "knowledge_base"
    source = kb_root / "AWS"
    source.mkdir(parents=True)

    unchanged_file = source / "a.md"
    unchanged_file.write_text("# A\n\ntext one", encoding="utf-8")

    baseline = datetime.now(timezone.utc)
    old_timestamp = (baseline - timedelta(minutes=5)).timestamp()
    unchanged_file.touch()
    unchanged_file.chmod(0o666)
    import os

    os.utime(unchanged_file, (old_timestamp, old_timestamp))

    registry = ParserRegistry()
    registry.register(".md", MarkdownParser(max_tokens=50, min_tokens=5))

    vector_store = FakeVectorStore()
    pipeline = IngestionPipeline(
        parser_registry=registry,
        embedding_service=FakeEmbeddingService(),
        vector_store=vector_store,
        knowledge_base_root=kb_root,
        source_dirs=["AWS"],
        last_successful_run_at=baseline,
        min_file_delta_seconds=0,
    )

    report = pipeline.run()

    assert report.total_files_discovered == 1
    assert report.total_files_ingested == 0
    assert report.skipped_duplicates == 0
    assert report.skipped_unchanged == 1
    assert len(vector_store.rows) == 0
