from services.api.services.vector_store import ChromaVectorStore


class FakeCollection:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[list[float], str, dict]] = {}

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        for idx, item_id in enumerate(ids):
            self.rows[item_id] = (embeddings[idx], documents[idx], metadatas[idx])

    def query(self, query_embeddings, n_results, include, where=None):
        query_vec = query_embeddings[0]

        def distance(v1: list[float], v2: list[float]) -> float:
            return sum(abs(a - b) for a, b in zip(v1, v2, strict=False))

        ordered = []
        for item_id, (emb, doc, meta) in self.rows.items():
            if where and any(meta.get(k) != v for k, v in where.items()):
                continue
            ordered.append((item_id, emb, doc, meta, distance(query_vec, emb)))

        ordered.sort(key=lambda row: row[4])
        sliced = ordered[:n_results]

        return {
            "ids": [[row[0] for row in sliced]],
            "documents": [[row[2] for row in sliced]],
            "metadatas": [[row[3] for row in sliced]],
            "distances": [[row[4] for row in sliced]],
        }

    def delete(self, ids) -> None:
        for item_id in ids:
            self.rows.pop(item_id, None)

    def count(self) -> int:
        return len(self.rows)

    def get(self, include=None):
        metadatas = [value[2] for value in self.rows.values()]
        return {"metadatas": metadatas}


def test_vector_store_roundtrip_upsert_query_delete() -> None:
    store = ChromaVectorStore(
        host="localhost",
        port=8000,
        collection_name="rag_knowledge_base",
        collection=FakeCollection(),
    )

    store.upsert(
        ids=["c1", "c2"],
        vectors=[[0.0, 0.0], [1.0, 1.0]],
        documents=["first", "second"],
        metadatas=[{"domain": "AWS"}, {"domain": "LULU"}],
    )

    assert store.count() == 2

    results = store.query(vector=[0.1, 0.1], k=1, where={"domain": "AWS"})
    assert len(results) == 1
    assert results[0]["id"] == "c1"
    assert results[0]["document"] == "first"

    store.delete(ids=["c1"])
    assert store.count() == 1
