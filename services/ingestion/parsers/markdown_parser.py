"""Markdown parser that produces structure-aware chunks."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import frontmatter
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    frontmatter = None

try:
    import mistune
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    mistune = None

from services.ingestion.chunking.token_counter import TokenCounter
from shared.models import Chunk, Document


logger = logging.getLogger(__name__)


class MarkdownParser:
    """Parse markdown files into a Document and token-bounded chunks."""

    def __init__(
        self,
        max_tokens: int = 1000,
        min_tokens: int = 100,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.token_counter = token_counter or TokenCounter()
        self._ast_parser = mistune.create_markdown(renderer="ast") if mistune is not None else None

    def parse(self, file_path: Path) -> tuple[Document, list[Chunk]]:
        """Parse markdown file into Document + list of Chunks."""
        logger.info("markdown_parse_started file_path=%s", file_path.as_posix())
        content = file_path.read_text(encoding="utf-8")
        metadata, markdown_body = self._extract_frontmatter(content)
        source_path = self._to_source_path(file_path)
        domain = self._extract_domain(source_path)

        content_hash = hashlib.sha256(markdown_body.encode("utf-8")).hexdigest()
        document_id = hashlib.sha256(f"{source_path}:{content_hash}".encode("utf-8")).hexdigest()

        stat = file_path.stat()
        created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        title = self._extract_title(markdown_body, file_path)
        doc = Document(
            id=document_id,
            source_path=source_path,
            domain=domain,
            title=title,
            content=markdown_body,
            content_hash=content_hash,
            created_at=created_at,
            modified_at=modified_at,
            tags=self._to_string_list(metadata.get("tags", [])),
            categories=self._to_string_list(metadata.get("categories", [])),
            frontmatter=metadata,
        )

        ast = self._ast_parser(markdown_body) if self._ast_parser is not None else self._simple_markdown_ast(markdown_body)
        chunks = self._build_chunks(ast, doc)
        chunks = self._merge_small_chunks(chunks, self.min_tokens)
        logger.info(
            "markdown_parse_completed file_path=%s domain=%s chunk_count=%s token_count=%s",
            file_path.as_posix(),
            doc.domain,
            len(chunks),
            sum(chunk.token_count for chunk in chunks),
        )
        return doc, chunks

    def _extract_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Extract YAML frontmatter and markdown body."""
        if frontmatter is not None:
            post = frontmatter.loads(content)
            return dict(post.metadata or {}), post.content

        return self._simple_frontmatter_parse(content)

    def _simple_frontmatter_parse(self, content: str) -> tuple[dict[str, Any], str]:
        if not content.startswith("---\n"):
            return {}, content

        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, content

        end_idx = None
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end_idx = idx
                break

        if end_idx is None:
            return {}, content

        metadata_lines = lines[1:end_idx]
        body = "\n".join(lines[end_idx + 1 :])
        metadata: dict[str, Any] = {}
        current_key: str | None = None

        for line in metadata_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("- ") and current_key is not None:
                metadata.setdefault(current_key, []).append(stripped[2:].strip())
                continue
            if ":" in stripped:
                key, raw_val = stripped.split(":", 1)
                key = key.strip()
                raw_val = raw_val.strip()
                current_key = key
                if raw_val:
                    metadata[key] = raw_val
                else:
                    metadata[key] = []

        return metadata, body

    def _simple_markdown_ast(self, markdown_body: str) -> list[dict[str, Any]]:
        tokens: list[dict[str, Any]] = []
        lines = markdown_body.splitlines()
        idx = 0

        while idx < len(lines):
            line = lines[idx]
            stripped = line.strip()

            if not stripped:
                idx += 1
                continue

            if stripped.startswith("```"):
                info = stripped[3:].strip() or None
                idx += 1
                code_lines: list[str] = []
                while idx < len(lines) and not lines[idx].strip().startswith("```"):
                    code_lines.append(lines[idx])
                    idx += 1
                if idx < len(lines):
                    idx += 1
                tokens.append(
                    {
                        "type": "block_code",
                        "raw": "\n".join(code_lines),
                        "attrs": {"info": info},
                    }
                )
                continue

            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                if level <= 6 and len(stripped) > level and stripped[level] == " ":
                    tokens.append(
                        {
                            "type": "heading",
                            "attrs": {"level": level},
                            "raw": stripped[level + 1 :].strip(),
                        }
                    )
                    idx += 1
                    continue

            paragraph_lines = [line]
            idx += 1
            while idx < len(lines):
                lookahead = lines[idx].strip()
                if not lookahead or lookahead.startswith("#") or lookahead.startswith("```"):
                    break
                paragraph_lines.append(lines[idx])
                idx += 1

            tokens.append({"type": "paragraph", "raw": "\n".join(paragraph_lines).strip()})

        return tokens

    def _build_chunks(self, ast: list[dict[str, Any]], doc: Document) -> list[Chunk]:
        """Build raw chunks by traversing markdown AST and splitting oversized chunks."""
        chunks: list[Chunk] = []
        heading_hierarchy: list[str] = [doc.domain]
        section_blocks: list[tuple[str, str, str | None]] = []

        for token in ast:
            token_type = token.get("type", "")
            if token_type == "heading":
                self._flush_section(chunks, section_blocks, heading_hierarchy, doc)
                self._update_heading_hierarchy(heading_hierarchy, token)
                continue

            if token_type == "block_code":
                self._flush_section(chunks, section_blocks, heading_hierarchy, doc)
                self._append_section_block(section_blocks, token, token_type)
                self._flush_section(chunks, section_blocks, heading_hierarchy, doc)
                continue

            self._append_section_block(section_blocks, token, token_type)

        self._flush_section(chunks, section_blocks, heading_hierarchy, doc)
        return self._normalize_chunk_indices(chunks, doc.id)

    def _flush_section(
        self,
        chunks: list[Chunk],
        section_blocks: list[tuple[str, str, str | None]],
        heading_hierarchy: list[str],
        doc: Document,
    ) -> None:
        if not section_blocks:
            return

        chunk_type, language, combined_text = self._compose_section_text(section_blocks)
        if not combined_text:
            section_blocks.clear()
            return

        base_chunk = Chunk(
            id=f"{doc.id}_{len(chunks)}",
            document_id=doc.id,
            domain=doc.domain,
            source_path=doc.source_path,
            text=combined_text,
            token_count=self.token_counter.count(combined_text),
            chunk_index=len(chunks),
            heading_hierarchy=heading_hierarchy.copy(),
            chunk_type=chunk_type,
            language=language,
            metadata={},
        )

        if base_chunk.chunk_type == "code" or base_chunk.token_count <= self.max_tokens:
            chunks.append(base_chunk)
        else:
            logger.info(
                "markdown_chunk_split document_id=%s source_path=%s token_count=%s max_tokens=%s",
                doc.id,
                doc.source_path,
                base_chunk.token_count,
                self.max_tokens,
            )
            chunks.extend(self._split_oversized_chunk(base_chunk, self.max_tokens))

        section_blocks.clear()

    def _compose_section_text(
        self,
        section_blocks: list[tuple[str, str, str | None]],
    ) -> tuple[str, str | None, str]:
        text_parts: list[str] = []
        language: str | None = None
        block_types = {block_type for block_type, _, _ in section_blocks}
        chunk_type = self._determine_chunk_type(block_types)

        for block_type, text, block_lang in section_blocks:
            if block_type == "code":
                if language is None:
                    language = block_lang
                text_parts.append(f"```{block_lang or ''}\n{text}\n```")
            else:
                text_parts.append(text)

        combined_text = "\n\n".join(part.strip() for part in text_parts if part.strip())
        return chunk_type, language, combined_text

    def _determine_chunk_type(self, block_types: set[str]) -> str:
        if block_types == {"code"}:
            return "code"
        if block_types == {"table"}:
            return "table"
        return "text"

    def _update_heading_hierarchy(self, heading_hierarchy: list[str], token: dict[str, Any]) -> None:
        level = int(token.get("attrs", {}).get("level", 1))
        heading_text = self._extract_text(token)
        if level > 3 or not heading_text:
            return

        target_len = level + 1
        while len(heading_hierarchy) > target_len:
            heading_hierarchy.pop()

        if len(heading_hierarchy) == target_len:
            heading_hierarchy[-1] = heading_text
            return

        heading_hierarchy.append(heading_text)

    def _to_source_path(self, file_path: Path) -> str:
        normalized = file_path.as_posix()
        marker = "/knowledge_base/"
        if marker in normalized:
            return normalized.split(marker, 1)[1]
        return file_path.name

    def _extract_domain(self, source_path: str) -> str:
        parts = [part for part in source_path.split("/") if part]
        if not parts:
            return "unknown"
        return parts[0]

    def _append_section_block(
        self,
        section_blocks: list[tuple[str, str, str | None]],
        token: dict[str, Any],
        token_type: str,
    ) -> None:
        if token_type == "block_code":
            section_blocks.append(("code", token.get("raw", "").strip(), token.get("attrs", {}).get("info")))
            return

        if token_type == "table":
            section_blocks.append(("table", self._table_to_text(token), None))
            return

        text = self._extract_text(token).strip()
        if text:
            section_blocks.append(("text", text, None))

    def _normalize_chunk_indices(self, chunks: list[Chunk], document_id: str) -> list[Chunk]:
        normalized: list[Chunk] = []
        for idx, chunk in enumerate(chunks):
            normalized.append(replace(chunk, chunk_index=idx, id=f"{document_id}_{idx}"))
        return normalized

    def _split_oversized_chunk(self, chunk: Chunk, max_tokens: int) -> list[Chunk]:
        """Split oversized chunks by paragraph boundaries."""
        paragraphs = [part.strip() for part in chunk.text.split("\n\n") if part.strip()]
        if len(paragraphs) <= 1:
            return [chunk]

        pieces: list[Chunk] = []
        buffer: list[str] = []

        for para in paragraphs:
            candidate = "\n\n".join(buffer + [para])
            if buffer and self.token_counter.count(candidate) > max_tokens:
                chunk_text = "\n\n".join(buffer)
                pieces.append(replace(chunk, text=chunk_text, token_count=self.token_counter.count(chunk_text)))
                buffer = [para]
            else:
                buffer.append(para)

        if buffer:
            chunk_text = "\n\n".join(buffer)
            pieces.append(replace(chunk, text=chunk_text, token_count=self.token_counter.count(chunk_text)))

        logger.info(
            "markdown_chunk_split_completed chunk_id=%s split_count=%s max_tokens=%s",
            chunk.id,
            len(pieces),
            max_tokens,
        )

        return pieces

    def _merge_small_chunks(self, chunks: list[Chunk], min_tokens: int) -> list[Chunk]:
        """Merge adjacent undersized non-code chunks while preserving hierarchy."""
        if not chunks:
            return []

        merged: list[Chunk] = []
        idx = 0
        while idx < len(chunks):
            current = chunks[idx]
            if (
                current.chunk_type == "code"
                or current.token_count >= min_tokens
                or idx + 1 >= len(chunks)
            ):
                merged.append(current)
                idx += 1
                continue

            nxt = chunks[idx + 1]
            if nxt.chunk_type == "code" or nxt.heading_hierarchy != current.heading_hierarchy:
                merged.append(current)
                idx += 1
                continue

            combined = f"{current.text}\n\n{nxt.text}"
            merged_chunk = replace(
                current,
                text=combined,
                token_count=self.token_counter.count(combined),
                metadata={**current.metadata, "merged_with": nxt.id},
            )
            merged.append(merged_chunk)
            idx += 2

        for new_idx, item in enumerate(merged):
            merged[new_idx] = replace(item, chunk_index=new_idx, id=f"{item.document_id}_{new_idx}")

        return merged

    def _extract_title(self, markdown_body: str, file_path: Path) -> str:
        for line in markdown_body.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return file_path.stem

    def _extract_text(self, token: dict[str, Any]) -> str:
        if "raw" in token and isinstance(token["raw"], str):
            return token["raw"]

        pieces: list[str] = []
        for child in token.get("children", []):
            pieces.append(self._extract_text(child))
        return "".join(pieces)

    def _table_to_text(self, token: dict[str, Any]) -> str:
        rows: list[str] = []
        for child in token.get("children", []):
            row_cells: list[str] = []
            for cell in child.get("children", []):
                row_cells.append(self._extract_text(cell).strip())
            if row_cells:
                rows.append(" | ".join(row_cells))
        return "\n".join(rows)

    def _to_string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if value in (None, ""):
            return []
        return [str(value)]
