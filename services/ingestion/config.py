"""Configuration settings for the ingestion service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    """Environment-backed ingestion configuration."""

    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "rag_knowledge_base"

    source_dirs: str = "AWS,LULU,Techno,Ahold,MyDocuments"
    knowledge_base_root: str = "/app/knowledge_base"
    ingestion_report_path: str = "/tmp/ingestion_report.json"
    ingestion_min_file_delta_seconds: int = 0
    max_chunk_tokens: int = 1000
    min_chunk_tokens: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def source_dir_list(self) -> list[str]:
        return [item.strip() for item in self.source_dirs.split(",") if item.strip()]
