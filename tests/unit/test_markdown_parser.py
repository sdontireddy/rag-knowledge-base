from pathlib import Path

from services.ingestion.parsers.markdown_parser import MarkdownParser


def test_markdown_parser_extracts_frontmatter_and_chunks(tmp_path: Path) -> None:
    md = """---
tags:
  - aws
  - bedrock
categories:
  - ai
---
# Bedrock Guide
## Intro
This is a markdown document for parser testing.

## Details
More details in another section.
"""
    file_path = tmp_path / "knowledge_base" / "AWS" / "Bedrock.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(md, encoding="utf-8")

    parser = MarkdownParser(max_tokens=40, min_tokens=5)
    document, chunks = parser.parse(file_path)

    assert document.domain == "AWS"
    assert document.source_path == "AWS/Bedrock.md"
    assert document.tags == ["aws", "bedrock"]
    assert document.categories == ["ai"]
    assert len(chunks) >= 1
    assert all(chunk.token_count <= 40 for chunk in chunks)


def test_markdown_parser_preserves_code_block_as_single_chunk(tmp_path: Path) -> None:
    md = """# Example

```python
for i in range(3):
    print(i)
```

A short paragraph after code.
"""
    file_path = tmp_path / "knowledge_base" / "AWS" / "Code.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(md, encoding="utf-8")

    parser = MarkdownParser(max_tokens=30, min_tokens=5)
    _, chunks = parser.parse(file_path)

    code_chunks = [chunk for chunk in chunks if chunk.chunk_type == "code"]
    assert len(code_chunks) == 1
    assert "for i in range(3):" in code_chunks[0].text
    assert "print(i)" in code_chunks[0].text
