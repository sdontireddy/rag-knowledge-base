import httpx

from services.ingestion.embedding_service import EmbeddingService


def test_embed_returns_embedding_vector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ollama:11434")
    service = EmbeddingService(
        ollama_base_url="http://ollama:11434",
        model="nomic-embed-text",
        client=client,
    )

    vector = service.embed("hello world")

    assert vector == [0.1, 0.2, 0.3]


def test_embed_retries_on_5xx_then_succeeds() -> None:
    state = {"attempt": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        state["attempt"] += 1
        if state["attempt"] < 3:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json={"embedding": [1.0, 2.0]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ollama:11434")
    service = EmbeddingService(
        ollama_base_url="http://ollama:11434",
        model="nomic-embed-text",
        max_retries=3,
        backoff_seconds=0,
        client=client,
    )

    vector = service.embed("retry me")

    assert vector == [1.0, 2.0]
    assert state["attempt"] == 3


def test_embed_batch_invokes_multiple_embeddings() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embedding": [0.5, 0.6]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ollama:11434")
    service = EmbeddingService(
        ollama_base_url="http://ollama:11434",
        model="nomic-embed-text",
        client=client,
    )

    vectors = service.embed_batch(["a", "b", "c"])

    assert vectors == [[0.5, 0.6], [0.5, 0.6], [0.5, 0.6]]
