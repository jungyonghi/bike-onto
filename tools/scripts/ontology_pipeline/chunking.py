# Timestamp: 2026-04-20 18:24:07

from __future__ import annotations

import re
from pathlib import Path

from .schemas import ChunkRecord


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _split_large_section(
    heading_path: list[str],
    body_text: str,
    max_chunk_chars: int,
    source_path: str,
    chunk_index_start: int,
) -> tuple[list[ChunkRecord], int]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body_text) if part.strip()]
    if not paragraphs:
        paragraphs = [body_text.strip()]

    chunks: list[ChunkRecord] = []
    current_parts: list[str] = []
    current_size = 0
    chunk_index = chunk_index_start

    def emit() -> None:
        nonlocal chunk_index, current_parts, current_size
        text = "\n\n".join(current_parts).strip()
        if not text:
            return
        chunks.append(
            ChunkRecord(
                chunk_id=f"chunk-{chunk_index:04d}",
                heading_path=heading_path[:] if heading_path else ["document"],
                text=text,
                source_path=source_path,
            )
        )
        chunk_index += 1
        current_parts = []
        current_size = 0

    for paragraph in paragraphs:
        paragraph_size = len(paragraph)
        if current_parts and current_size + paragraph_size + 2 > max_chunk_chars:
            emit()
        if paragraph_size > max_chunk_chars:
            for start in range(0, paragraph_size, max_chunk_chars):
                part = paragraph[start : start + max_chunk_chars]
                chunks.append(
                    ChunkRecord(
                        chunk_id=f"chunk-{chunk_index:04d}",
                        heading_path=heading_path[:] if heading_path else ["document"],
                        text=part,
                        source_path=source_path,
                    )
                )
                chunk_index += 1
            continue
        current_parts.append(paragraph)
        current_size += paragraph_size + 2

    emit()
    return chunks, chunk_index


def chunk_markdown_by_heading(
    text: str,
    max_chunk_chars: int = 12000,
    source_path: str | Path = "",
) -> list[ChunkRecord]:
    source_text = str(source_path)
    heading_stack: list[str] = []
    current_path: list[str] = []
    buffer: list[str] = []
    all_chunks: list[ChunkRecord] = []
    chunk_index = 1

    def flush_buffer() -> None:
        nonlocal buffer, chunk_index
        body = "".join(buffer).strip()
        if not body:
            buffer = []
            return
        new_chunks, chunk_index = _split_large_section(
            heading_path=current_path,
            body_text=body,
            max_chunk_chars=max_chunk_chars,
            source_path=source_text,
            chunk_index_start=chunk_index,
        )
        all_chunks.extend(new_chunks)
        buffer = []

    for line in text.splitlines(keepends=True):
        heading_match = HEADING_RE.match(line.strip("\n"))
        if heading_match:
            flush_buffer()
            level = len(heading_match.group(1))
            heading_title = heading_match.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(heading_title)
            current_path = heading_stack[:]
            continue
        buffer.append(line)

    flush_buffer()
    if not all_chunks and text.strip():
        all_chunks, _ = _split_large_section(
            heading_path=["document"],
            body_text=text.strip(),
            max_chunk_chars=max_chunk_chars,
            source_path=source_text,
            chunk_index_start=1,
        )
    return all_chunks
