import httpx

from services.api.services.answer_generator import AnswerGenerator


class FakeClient:
    def __init__(self, response_text: str, status_code: int = 200) -> None:
        self.response_text = response_text
        self.status_code = status_code

    def post(self, url, json, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(
            status_code=self.status_code,
            request=request,
            json={"response": self.response_text},
        )


def test_answer_generator_returns_valid_cited_answer() -> None:
    generator = AnswerGenerator(
        ollama_base_url="http://localhost:11434",
        model="llama3:8b",
        client=FakeClient("ANSWER:\nEnable access in the console [c1]\nCITATIONS:\nc1"),
    )

    result = generator.generate(
        query="How do I enable Bedrock?",
        context_chunks=[
            {
                "chunk_id": "c1",
                "source_path": "AWS/Bedrock.md",
                "domain": "AWS",
                "section": "AWS > Bedrock",
                "text": "Enable access in the console.",
                "relevance_score": 0.9,
            }
        ],
    )

    assert result["answer_text"] == "Enable access in the console [c1]"
    assert len(result["citations"]) == 1
    assert result["citations"][0]["chunk_id"] == "c1"
    assert len(result["context_chunks"]) == 1


def test_answer_generator_rejects_uncited_output() -> None:
    generator = AnswerGenerator(
        ollama_base_url="http://localhost:11434",
        model="llama3:8b",
        client=FakeClient("ANSWER:\nEnable access in the console\nCITATIONS:\nc1"),
    )

    result = generator.generate(
        query="How do I enable Bedrock?",
        context_chunks=[
            {
                "chunk_id": "c1",
                "source_path": "AWS/Bedrock.md",
                "domain": "AWS",
                "section": "AWS > Bedrock",
                "text": "Enable access in the console.",
                "relevance_score": 0.9,
            }
        ],
    )

    assert result["answer_text"] != "INSUFFICIENT_CONTEXT"
    assert len(result["citations"]) == 1
    assert result["citations"][0]["chunk_id"] == "c1"


def test_answer_generator_returns_insufficient_context_when_no_chunks() -> None:
    generator = AnswerGenerator(ollama_base_url="http://localhost:11434", model="llama3:8b")

    result = generator.generate(query="What is the rollback plan?", context_chunks=[])

    assert result["answer_text"] == "INSUFFICIENT_CONTEXT"
    assert result["citations"] == []
    assert result["context_chunks"] == []


def test_answer_generator_rejects_when_any_sentence_lacks_citation() -> None:
    generator = AnswerGenerator(
        ollama_base_url="http://localhost:11434",
        model="llama3:8b",
        client=FakeClient("ANSWER:\nEnable access [c1]. Then run validation.\nCITATIONS:\nc1"),
    )

    result = generator.generate(
        query="How do I enable Bedrock?",
        context_chunks=[
            {
                "chunk_id": "c1",
                "source_path": "AWS/Bedrock.md",
                "domain": "AWS",
                "section": "AWS > Bedrock",
                "text": "Enable access in the console.",
                "relevance_score": 0.9,
            }
        ],
    )

    assert result["answer_text"] != "INSUFFICIENT_CONTEXT"
    assert len(result["citations"]) == 1
    assert result["citations"][0]["chunk_id"] == "c1"


def test_answer_generator_returns_insufficient_context_for_unrelated_query() -> None:
    generator = AnswerGenerator(
        ollama_base_url="http://localhost:11434",
        model="llama3:8b",
        client=FakeClient("ANSWER:\nGeneral answer with no citations\nCITATIONS:\nNONE"),
    )

    result = generator.generate(
        query="kubernetes autoscaling policy",
        context_chunks=[
            {
                "chunk_id": "c1",
                "source_path": "AWS/Bedrock.md",
                "domain": "AWS",
                "section": "AWS > Bedrock",
                "text": "Enable access in the console.",
                "relevance_score": 0.9,
            }
        ],
    )

    assert result["answer_text"] == "INSUFFICIENT_CONTEXT"
    assert result["citations"] == []