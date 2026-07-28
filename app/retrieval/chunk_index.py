"""Permission-aware lexical + semantic retrieval over chunk metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.auth.profiles import UserProfile
from app.ingestion.build_index import DEFAULT_FAISS_PATH, DEFAULT_METADATA_PATH
from app.retrieval.access import can_access_metadata
from app.retrieval.config import HybridRetrievalConfig
from app.retrieval.embeddings import (
    EmbeddingProvider,
    LocalSemanticEmbeddingProvider,
    cosine_similarity,
)
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
    """A public retrieval result with backward-compatible ``score`` metadata."""

    chunk: Chunk
    score: float
    snippet: str
    lexical_score: float = 0.0
    semantic_score: float = 0.0


class MetadataChunkRetriever:
    """Hybrid retriever with authorization before candidate scoring/output.

    The old FAISS file was built from token-hash vectors.  Hash vectors are not
    semantic embeddings, so this retriever deliberately does not read that
    legacy index.  The default semantic path is local LSA from
    :mod:`app.retrieval.embeddings`; an injected provider can replace it for
    tests or an explicitly managed deployment provider.
    """

    def __init__(
        self,
        metadata_path: Path = DEFAULT_METADATA_PATH,
        faiss_path: Path = DEFAULT_FAISS_PATH,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        config: HybridRetrievalConfig | None = None,
    ) -> None:
        self.metadata_path = metadata_path
        # Retained for constructor compatibility and rebuild tooling.  Legacy
        # hash-vector FAISS files are intentionally not an active backend.
        self.faiss_path = faiss_path
        self.config = config or HybridRetrievalConfig.from_env()
        self.chunks = tuple(load_chunks(metadata_path))
        self._embedding_error: str | None = None
        if embedding_provider is not None:
            self._embedding_provider: EmbeddingProvider | None = embedding_provider
        elif self.chunks:
            try:
                self._embedding_provider = LocalSemanticEmbeddingProvider(tuple(chunk.text for chunk in self.chunks))
            except Exception as exc:  # noqa: BLE001 - lexical search remains safe.
                self._embedding_provider = None
                self._embedding_error = type(exc).__name__
        else:
            self._embedding_provider = None
        self._document_embedding_cache: dict[int, tuple[float, ...]] = {}

    def available(self) -> bool:
        return bool(self.chunks)

    def vector_available(self) -> bool:
        return self._embedding_provider is not None and self._embedding_error is None

    def backend_name(self) -> str:
        if not self.vector_available():
            return "metadata_lexical"
        return f"hybrid_{_provider_name(self._embedding_provider)}"

    def safe_metadata(self) -> dict[str, object]:
        provider = self._embedding_provider
        metadata: dict[str, object] = {
            "backend": self.backend_name(),
            "semantic_available": self.vector_available(),
            "legacy_hash_vectors_active": False,
            "embedding_error": self._embedding_error,
            "config": self.config.safe_metadata(),
        }
        provider_metadata = getattr(provider, "safe_metadata", None)
        if callable(provider_metadata):
            details = provider_metadata()
            if isinstance(details, dict):
                metadata["embedding"] = dict(details)
        return metadata

    def search(self, query: str, profile: UserProfile, max_results: int = 4) -> tuple[ChunkSearchResult, ...]:
        terms = _tokenize(query)
        if not terms or max_results <= 0:
            return ()

        # Filter before semantic provider calls and before any candidate can
        # become a result.  Restricted chunks never reach an injected provider
        # during query-time retrieval and never reach answer composition.
        accessible = tuple(
            (index, chunk)
            for index, chunk in enumerate(self.chunks)
            if can_access_chunk(profile, chunk)
        )
        if not accessible:
            return ()

        lexical_raw = {
            index: float(_lexical_score(chunk, query, terms))
            for index, chunk in accessible
        }
        semantic_raw = self._semantic_scores(query, accessible)
        lexical_max = max(lexical_raw.values(), default=0.0)
        lexical_normalized = {
            index: (score / lexical_max if lexical_max else 0.0)
            for index, score in lexical_raw.items()
        }

        lexical_pool = _top_indices(
            lexical_raw,
            accessible,
            self.config.lexical_candidate_count,
        )
        semantic_pool = _top_indices(
            semantic_raw,
            accessible,
            self.config.semantic_candidate_count,
        )
        candidate_indexes = lexical_pool | semantic_pool
        if not candidate_indexes:
            return ()

        weight_total = self.config.lexical_weight + self.config.semantic_weight
        lexical_weight = self.config.lexical_weight / weight_total
        semantic_weight = self.config.semantic_weight / weight_total
        results: list[ChunkSearchResult] = []
        accessible_by_index = dict(accessible)
        for index in candidate_indexes:
            lexical_score = lexical_normalized.get(index, 0.0)
            semantic_score = semantic_raw.get(index, 0.0)
            score = lexical_weight * lexical_score + semantic_weight * semantic_score
            if score <= 0.0:
                continue
            chunk = accessible_by_index[index]
            results.append(
                ChunkSearchResult(
                    chunk=chunk,
                    score=float(score),
                    snippet=_snippet(chunk.text, terms),
                    lexical_score=float(lexical_score),
                    semantic_score=float(semantic_score),
                )
            )

        # Sort before document de-duplication so the strongest chunk represents
        # each document.  All keys after scores are stable and data-derived.
        results.sort(key=_result_sort_key)
        limit = min(max_results, self.config.max_results)
        return tuple(_dedupe_by_doc(results)[:limit])

    def _semantic_scores(
        self,
        query: str,
        accessible: tuple[tuple[int, Chunk], ...],
    ) -> dict[int, float]:
        provider = self._embedding_provider
        if provider is None:
            return {}
        try:
            query_vector = provider.embed_query(query)
            document_vectors = self._document_vectors(provider, accessible)
        except Exception as exc:  # noqa: BLE001 - semantic failure falls back safely.
            self._embedding_error = type(exc).__name__
            return {}

        scores: dict[int, float] = {}
        for index, vector in document_vectors.items():
            # Negative cosine is dissimilar, not useful positive relevance.
            scores[index] = max(0.0, cosine_similarity(query_vector, vector))
        return scores

    def _document_vectors(
        self,
        provider: EmbeddingProvider,
        accessible: tuple[tuple[int, Chunk], ...],
    ) -> dict[int, tuple[float, ...]]:
        local_vectors = getattr(provider, "document_vectors", None)
        if callable(local_vectors):
            fitted = tuple(local_vectors())
            if len(fitted) == len(self.chunks):
                for index, _chunk in accessible:
                    self._document_embedding_cache[index] = tuple(float(value) for value in fitted[index])

        missing = [(index, chunk) for index, chunk in accessible if index not in self._document_embedding_cache]
        if missing:
            vectors = provider.embed_documents([chunk.text for _index, chunk in missing])
            if len(vectors) != len(missing):
                raise ValueError("embedding provider returned the wrong document count")
            for (index, _chunk), vector in zip(missing, vectors, strict=True):
                self._document_embedding_cache[index] = tuple(float(value) for value in vector)
        return {index: self._document_embedding_cache[index] for index, _chunk in accessible}


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
    return can_access_metadata(
        profile,
        department=chunk.department,
        confidentiality=chunk.confidentiality,
        allowed_roles=chunk.allowed_roles,
        allowed_groups=chunk.allowed_groups,
        allowed_users=chunk.allowed_users,
    )


def _provider_name(provider: EmbeddingProvider) -> str:
    name = str(getattr(provider, "name", "custom")).strip().lower()
    return re.sub(r"[^a-z0-9_-]+", "_", name) or "custom"


def _top_indices(
    scores: dict[int, float],
    accessible: tuple[tuple[int, Chunk], ...],
    limit: int,
) -> set[int]:
    positive = [
        (index, score, chunk)
        for index, chunk in accessible
        if (score := scores.get(index, 0.0)) > 0.0
    ]
    positive.sort(key=lambda item: (-item[1], item[2].doc_id, item[2].chunk_index, item[2].chunk_id))
    return {index for index, _score, _chunk in positive[:limit]}


def _result_sort_key(item: ChunkSearchResult) -> tuple[float, float, float, str, int, str]:
    return (
        -item.score,
        -item.lexical_score,
        -item.semantic_score,
        item.chunk.doc_id,
        item.chunk.chunk_index,
        item.chunk.chunk_id,
    )


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
