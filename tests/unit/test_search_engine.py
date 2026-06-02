from services.api.services.search_engine import SearchEngine


class FakeEmbeddingService:
    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2]


class FakeVectorStore:
    def query(self, vector, k, where=None):
        assert vector == [0.1, 0.2]
        data = [
            {
                "id": "c1",
                "document": "aws text",
                "metadata": {
                    "source_path": "AWS/Bedrock.md",
                    "domain": "AWS",
                    "heading_hierarchy": "AWS > Bedrock",
                },
                "distance": 0.1,
            },
            {
                "id": "c2",
                "document": "lulu text",
                "metadata": {
                    "source_path": "LULU/Notes.md",
                    "domain": "LULU",
                    "heading_hierarchy": "LULU > Notes",
                },
                "distance": 0.8,
            },
        ]
        if where is not None:
            data = [item for item in data if item["metadata"].get("domain") == where.get("domain")]
        return data[:k]


def test_search_engine_ranks_and_filters_results() -> None:
    engine = SearchEngine(embedding_service=FakeEmbeddingService(), vector_store=FakeVectorStore())

    results = engine.search(query="bedrock", k=5, domain_filter=["AWS"], min_score=0.0)

    assert len(results) == 1
    assert results[0]["domain"] == "AWS"
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["relevance_score"] > 0.5


def test_search_engine_applies_min_score() -> None:
    engine = SearchEngine(embedding_service=FakeEmbeddingService(), vector_store=FakeVectorStore())

    results = engine.search(query="all", k=5, domain_filter=None, min_score=0.7)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"


def test_search_engine_promotes_keyword_overlap_for_totecontent_query() -> None:
    class ToteContentVectorStore:
        def query(self, vector, k, where=None):
            return [
                {
                    "id": "generic",
                    "document": "General architecture content",
                    "metadata": {
                        "source_path": "AWS/CloudFront.md",
                        "domain": "AWS",
                        "heading_hierarchy": "AWS > CloudFront",
                    },
                    "distance": 0.05,
                },
                {
                    "id": "tote",
                    "document": "Deployment steps for Tote Content release.",
                    "metadata": {
                        "source_path": "MAWM/ToteContent/ToteContent_Deployment_Steps_Next_Release.md",
                        "domain": "MAWM",
                        "heading_hierarchy": "MAWM > ToteContent > Deployment",
                    },
                    "distance": 0.3,
                },
            ]

    engine = SearchEngine(embedding_service=FakeEmbeddingService(), vector_store=ToteContentVectorStore())
    results = engine.search(query="Give me ToteContent Deployment details", k=2, domain_filter=None, min_score=0.0)

    assert len(results) == 2
    assert results[0]["chunk_id"] == "tote"
