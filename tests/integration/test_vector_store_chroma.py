import pytest

from services.api.services.vector_store import ChromaVectorStore


@pytest.mark.integration
def test_chroma_vector_store_roundtrip_real_client() -> None:
    chromadb = pytest.importorskip("chromadb")

    client = chromadb.Client()
    collection = client.get_or_create_collection(name="rag_kb_test")
    collection.delete(where={})

    store = ChromaVectorStore(
        host="localhost",
        port=8000,
        collection_name="rag_kb_test",
        collection=collection,
    )

    store.upsert(
        ids=["a", "b"],
        vectors=[[0.0, 0.0], [1.0, 1.0]],
        documents=["first", "second"],
        metadatas=[
            {"domain": "AWS", "document_id": "doc-a", "source_path": "AWS/a.md"},
            {"domain": "LULU", "document_id": "doc-b", "source_path": "LULU/b.md"},
        ],
    )

    assert store.count() == 2

    results = store.query(vector=[0.05, 0.05], k=1, where={"domain": "AWS"})
    assert len(results) == 1
    assert results[0]["id"] == "a"

    store.delete(ids=["a"])
    assert store.count() == 1
