"""Permission-aware retrieval over generated RAG chunk metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.auth.profiles import UserProfile
from app.ingestion.build_index import DEFAULT_FAISS_PATH, DEFAULT_METADATA_PATH, _hash_embedding
from app.retrieval.local_kb import Citation, _tokenize


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    title: str
    source_type: str
    source_path: str
    department: str
    confidentiality: str
    allowed_roles: tuple[str, ...]
    allowed_groups: tuple[str, ...]
    allowed_users: tuple[str, ...]
    updated_at: str
    text: str
    token_estimate: int

    @property
    def citation(self) -> Citation:
        return Citation(
            doc_id=self.doc_id,
            title=self.title,
            source_type=self.source_type,
            source_path=self.source_path,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True)
class ChunkSearchResult:
    chunk: Chunk
    score: float
    snippet: str


class MetadataChunkRetriever:
    """Permission-aware hybrid retriever over generated chunk metadata and FAISS."""

    def __init__(self, metadata_path: Path = DEFAULT_METADATA_PATH, faiss_path: Path = DEFAULT_FAISS_PATH) -> None:
        self.metadata_path = metadata_path
        self.faiss_path = faiss_path
        self.chunks = tuple(load_chunks(metadata_path))
        self._faiss_index = _load_faiss_index(faiss_path, expected_size=len(self.chunks))

    def available(self) -> bool:
        return bool(self.chunks)

    def vector_available(self) -> bool:
        return self._faiss_index is not None

    def backend_name(self) -> str:
        return "faiss_hybrid" if self.vector_available() else "metadata_lexical"

    def search(self, query: str, profile: UserProfile, max_results: int = 4) -> tuple[ChunkSearchResult, ...]:
        terms = _tokenize(query)
        if not terms:
            return ()
        if self._faiss_index is not None:
            return self._hybrid_search(query, terms, profile, max_results)
        return self._lexical_search(query, terms, profile, max_results)

    def _lexical_search(
        self,
        query: str,
        terms: tuple[str, ...],
        profile: UserProfile,
        max_results: int,
    ) -> tuple[ChunkSearchResult, ...]:
        results: list[ChunkSearchResult] = []
        for chunk in self.chunks:
            if not can_access_chunk(profile, chunk):
                continue
            score = _lexical_score(chunk, query, terms)
            if score <= 0:
                continue
            results.append(ChunkSearchResult(chunk=chunk, score=float(score), snippet=_snippet(chunk.text, terms)))
        results.sort(key=lambda item: (item.score, item.chunk.updated_at), reverse=True)
        return tuple(_dedupe_by_doc(results)[:max_results])

    def _hybrid_search(
        self,
        query: str,
        terms: tuple[str, ...],
        profile: UserProfile,
        max_results: int,
    ) -> tuple[ChunkSearchResult, ...]:
        import numpy as np

        vector = np.array([_hash_embedding(query)], dtype="float32")
        candidate_count = min(len(self.chunks), max(50, max_results * 10))
        scores, indexes = self._faiss_index.search(vector, candidate_count)
        candidates: dict[int, float] = {}
        for raw_index, raw_score in zip(indexes[0], scores[0], strict=False):
            index = int(raw_index)
            if index < 0:
                continue
            candidates[index] = max(candidates.get(index, 0.0), float(raw_score))

        for index, chunk in enumerate(self.chunks):
            lexical_score = _lexical_score(chunk, query, terms)
            if lexical_score > 0:
                candidates[index] = candidates.get(index, 0.0) + float(lexical_score)

        results: list[ChunkSearchResult] = []
        for index, score in candidates.items():
            chunk = self.chunks[index]
            if not can_access_chunk(profile, chunk):
                continue
            if score <= 0:
                continue
            results.append(ChunkSearchResult(chunk=chunk, score=score, snippet=_snippet(chunk.text, terms)))
        results.sort(key=lambda item: (item.score, item.chunk.updated_at), reverse=True)
        return tuple(_dedupe_by_doc(results)[:max_results])


def load_chunks(metadata_path: Path = DEFAULT_METADATA_PATH) -> list[Chunk]:
    if not metadata_path.exists():
        return []
    chunks: list[Chunk] = []
    with metadata_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            chunks.append(
                Chunk(
                    chunk_id=str(payload["chunk_id"]),
                    doc_id=str(payload["doc_id"]),
                    chunk_index=int(payload["chunk_index"]),
                    title=str(payload["title"]),
                    source_type=str(payload["source_type"]),
                    source_path=str(payload["source_path"]),
                    department=str(payload["department"]),
                    confidentiality=str(payload["confidentiality"]),
                    allowed_roles=tuple(payload.get("allowed_roles", ())),
                    allowed_groups=tuple(payload.get("allowed_groups", ())),
                    allowed_users=tuple(payload.get("allowed_users", ())),
                    updated_at=str(payload["updated_at"]),
                    text=str(payload["text"]),
                    token_estimate=int(payload["token_estimate"]),
                )
            )
    return chunks


def can_access_chunk(profile: UserProfile, chunk: Chunk) -> bool:
    if profile.status != "active":
        return False
    if profile.user_id in chunk.allowed_users:
        return True
    if profile.role in chunk.allowed_roles:
        return True
    return bool(set(profile.groups).intersection(chunk.allowed_groups))


def _load_faiss_index(faiss_path: Path, expected_size: int):
    if not faiss_path.exists() or expected_size <= 0:
        return None
    try:
        import faiss  # type: ignore[import-not-found]
    except ImportError:
        return None
    index = faiss.read_index(str(faiss_path))
    if index.ntotal != expected_size:
        return None
    return index


def _lexical_score(chunk: Chunk, query: str, terms: tuple[str, ...]) -> int:
    title = chunk.title.lower()
    body = chunk.text.lower()
    score = sum(body.count(term) for term in terms)
    score += sum(title.count(term) * 6 for term in terms)
    topic_terms = [term for term in terms if term not in {"access", "request", "policy", "process"}]
    score += sum(title.count(term) * 10 for term in topic_terms)
    for phrase in _topic_phrases(query, terms):
        if phrase in title:
            score += 30
        elif phrase in body:
            score += 8
    return score


def _topic_phrases(query: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    lowered = query.lower()
    phrases = []
    for first, second in zip(terms, terms[1:], strict=False):
        phrase = f"{first} {second}"
        if phrase in lowered:
            phrases.append(phrase)
    return tuple(phrases)


def build_answer_from_chunks(query: str, results: tuple[ChunkSearchResult, ...]) -> str:
    if not results:
        return (
            "I do not have enough accessible source context to answer that confidently. "
            "Try asking about a public policy, an internal process, or your own support tickets."
        )
    top = results[0]
    lines = [f"From {top.chunk.title} [1]:"]
    lines.append(top.snippet)
    if len(results) > 1:
        related = ", ".join(f"{result.chunk.title} [{index}]" for index, result in enumerate(results[1:], start=2))
        lines.append(f"Related accessible sources: {related}.")
    return "\n\n".join(lines)


def _dedupe_by_doc(results: Iterable[ChunkSearchResult]) -> list[ChunkSearchResult]:
    seen: set[str] = set()
    deduped: list[ChunkSearchResult] = []
    for result in results:
        if result.chunk.doc_id in seen:
            continue
        seen.add(result.chunk.doc_id)
        deduped.append(result)
    return deduped


def _snippet(text: str, terms: tuple[str, ...]) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return ""
    scored = sorted(
        (
            (
                sum(paragraph.lower().count(term) for term in terms),
                _snippet_quality(paragraph),
                paragraph,
            )
            for paragraph in paragraphs
        ),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    snippet = scored[0][2] if scored[0][0] > 0 else paragraphs[0]
    return re.sub(r"^#+\s*", "", snippet.replace("`", ""), flags=re.MULTILINE).strip()


def _snippet_quality(paragraph: str) -> int:
    quality = 0
    if re.search(r"(?m)^\s*\d+\.", paragraph):
        quality += 10
    if re.search(r"(?m)^\s*[-*]\s+", paragraph):
        quality += 4
    if paragraph.lstrip().startswith("#"):
        quality -= 5
    if len(paragraph.split()) > 12:
        quality += 2
    return quality
