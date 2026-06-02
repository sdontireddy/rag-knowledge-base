from services.ingestion.chunking.chunker import TextChunker


def test_split_paragraphs_respects_max_tokens() -> None:
    chunker = TextChunker(max_tokens=10, min_tokens=5)
    text = "\n\n".join(
        [
            "one two three four five",
            "six seven eight nine ten",
            "eleven twelve thirteen fourteen fifteen",
        ]
    )

    chunks = chunker.split_paragraphs(text)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunker.token_counter.count(chunk) <= chunker.max_tokens


def test_merge_small_combines_adjacent_chunks() -> None:
    chunker = TextChunker(max_tokens=50, min_tokens=8)
    chunks = ["one two", "three four", "five six seven eight nine ten"]

    merged = chunker.merge_small(chunks)

    assert len(merged) < len(chunks)
    assert "one two\n\nthree four" in merged[0]
