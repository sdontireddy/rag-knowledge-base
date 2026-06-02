from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.api.routers.search import router as search_router


class FakeSearchEngine:
    def search(self, query, k, domain_filter, min_score):
        return [
            {
                "chunk_id": "c1",
                "text": "sample text",
                "source_path": "AWS/Bedrock.md",
                "domain": "AWS",
                "section": "AWS > Bedrock",
                "relevance_score": 0.9,
                "rank": 1,
            }
        ]


class FakeAnswerGenerator:
    def generate(self, query, context_chunks, max_tokens):
        assert query == "bedrock"
        assert len(context_chunks) == 1
        return {
            "answer_text": "Use model access [c1]",
            "citations": [context_chunks[0]],
            "context_chunks": context_chunks,
            "model": "llama3:8b",
            "generation_time_ms": 12,
        }


class FailingAnswerGenerator:
    model = "tinyllama:latest"

    def generate(self, query, context_chunks, max_tokens):
        raise RuntimeError("timed out")


def test_post_search_returns_expected_fields() -> None:
    app = FastAPI()
    app.include_router(search_router)
    app.state.search_engine = FakeSearchEngine()

    client = TestClient(app)
    response = client.post(
        "/api/search",
        json={"query": "bedrock", "k": 5, "domain_filter": ["AWS"], "min_score": 0.0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "bedrock"
    assert len(payload["results"]) == 1
    item = payload["results"][0]
    assert item["chunk_id"] == "c1"
    assert item["source_path"] == "AWS/Bedrock.md"
    assert item["domain"] == "AWS"
    assert item["section"] == "AWS > Bedrock"
    assert "relevance_score" in item


def test_post_answer_returns_grounded_answer_with_citations() -> None:
    app = FastAPI()
    app.include_router(search_router)
    app.state.search_engine = FakeSearchEngine()
    app.state.answer_generator = FakeAnswerGenerator()

    client = TestClient(app)
    response = client.post(
        "/api/answer",
        json={"query": "bedrock", "k": 5, "domain_filter": ["AWS"], "max_tokens": 256},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "bedrock"
    assert payload["answer_text"] == "Use model access [c1]"
    assert payload["model"] == "llama3:8b"
    assert payload["generation_time_ms"] == 12
    assert len(payload["citations"]) == 1
    assert payload["citations"][0]["chunk_id"] == "c1"
    assert len(payload["context_chunks"]) == 1
    assert payload["context_chunks"][0]["chunk_id"] == "c1"


def test_post_answer_degrades_gracefully_on_generation_error() -> None:
    app = FastAPI()
    app.include_router(search_router)
    app.state.search_engine = FakeSearchEngine()
    app.state.answer_generator = FailingAnswerGenerator()

    client = TestClient(app)
    response = client.post(
        "/api/answer",
        json={"query": "bedrock", "k": 5, "domain_filter": ["AWS"], "max_tokens": 256},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_text"] == "INSUFFICIENT_CONTEXT"
    assert payload["citations"] == []
    assert payload["model"] == "tinyllama:latest"
    assert payload["generation_time_ms"] == 0
    assert len(payload["context_chunks"]) == 1
