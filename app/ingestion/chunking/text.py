"""Deterministic text chunking for Markdown/PDF-source documents."""

from __future__ import annotations

import re


def chunk_text(text: str, max_chars: int = 1200, overlap_chars: int = 160) -> tuple[str, ...]:
    """Split text into stable chunks without requiring tokenizer dependencies."""

    normalized = _normalize_text(text)
    if not normalized:
        return ()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = _with_overlap(chunks[-1], overlap_chars, paragraph) if chunks and overlap_chars else paragraph
            if len(current) > max_chars:
                current = paragraph
        else:
            split_parts = _split_long_paragraph(paragraph, max_chars)
            chunks.extend(split_parts[:-1])
            current = split_parts[-1]
    if current:
        chunks.append(current)
    return tuple(chunk for chunk in chunks if chunk.strip())


def _normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
    return "\n".join(lines).strip()


def _with_overlap(previous: str, overlap_chars: int, paragraph: str) -> str:
    overlap = previous[-overlap_chars:].strip()
    return f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = sentence
    if current:
        parts.append(current)
    return parts or [paragraph[:max_chars]]
