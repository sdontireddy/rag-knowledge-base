"""Configuration settings for API service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed API configuration."""

    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3:8b"
    embedding_model: str = "nomic-embed-text"

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "rag_knowledge_base"

    default_k: int = 5
    min_relevance_score: float = 0.0
    max_answer_tokens: int = 1024
    answer_timeout_seconds: int = 10

    api_host: str = "0.0.0.0"
    api_port: int = 8080
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
