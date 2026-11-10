from __future__ import annotations

import re
from dataclasses import dataclass


class ChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    metadata: dict[str, int]


def _split_long_unit(text: str, chunk_size: int) -> list[str]:
    words = text.split()
    parts: list[str] = []
    current = ""
    for word in words:
        if len(word) > chunk_size:
            if current:
                parts.append(current)
                current = ""
            parts.extend(
                word[start : start + chunk_size]
                for start in range(0, len(word), chunk_size)
            )
            continue
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > chunk_size:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _overlap_suffix(text: str, overlap: int) -> str:
    if overlap == 0:
        return ""
    suffix = text[-overlap:]
    first_boundary = suffix.find(" ")
    if first_boundary >= 0:
        suffix = suffix[first_boundary + 1 :]
    return suffix.strip()


def _chunk_page(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    units = [
        part
        for sentence in sentences
        for part in _split_long_unit(sentence.strip(), chunk_size)
        if part
    ]
    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current} {unit}".strip()
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            prefix = _overlap_suffix(current, overlap)
            current = f"{prefix} {unit}".strip()
            if len(current) > chunk_size:
                chunks.append(prefix)
                current = unit
        else:
            current = unit
    if current:
        chunks.append(current)
    return chunks


def chunk_pages(
    pages: tuple[str, ...] | list[str],
    *,
    chunk_size: int,
    overlap: int,
) -> list[TextChunk]:
    if chunk_size < 1:
        raise ChunkingError("Chunk size must be at least one")
    if overlap < 0 or overlap >= chunk_size:
        raise ChunkingError("Overlap must be non-negative and smaller than chunk size")
    chunks: list[TextChunk] = []
    for page_number, text in enumerate(pages, start=1):
        for chunk_text in _chunk_page(text, chunk_size, overlap):
            if chunk_text:
                chunks.append(
                    TextChunk(
                        index=len(chunks),
                        text=chunk_text,
                        metadata={"page_number": page_number},
                    )
                )
    return chunks
