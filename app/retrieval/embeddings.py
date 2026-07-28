"""Local semantic embeddings used by the hybrid retriever.

The default provider is corpus-trained latent semantic analysis (LSA).  It is
not a token hash or a pretending-to-be-semantic vector: TF-IDF document-term
vectors are projected into a small latent space with SVD, and query/document
cosine similarity is calculated in that space.  It needs only NumPy and the
local indexed text; it never calls a hosted service or downloads a model.

A retriever can receive an injected provider implementing the small protocol
below.  That keeps production provider choices explicit and makes offline
retrieval tests deterministic without credentials.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Minimal provider contract for query and document vectors."""

    @property
    def name(self) -> str: ...

    def embed_query(self, text: str) -> Sequence[float]: ...

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class EmbeddingUnavailableError(RuntimeError):
    """Raised when a local semantic dependency cannot be loaded."""


class LocalSemanticEmbeddingProvider:
    """Dependency-light, corpus-trained distributional semantic embedder.

    LSA is intentionally modest compared with a neural sentence-transformer:
    it can connect terms that occur in related local documents, but it cannot
    infer arbitrary world knowledge or multilingual meaning.  It is still a
    genuine learned latent-space similarity path and is preferable to the old
    deterministic token-hash vectors, which have been removed from indexing.
    """

    name = "local_lsa"

    def __init__(self, corpus_texts: Sequence[str], dimensions: int = 64) -> None:
        if dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - depends on deployment image.
            raise EmbeddingUnavailableError("numpy is not installed") from exc

        self._np = np
        self._dimensions = dimensions
        tokenized = [_semantic_tokens(text) for text in corpus_texts]
        vocabulary = sorted({token for tokens in tokenized for token in tokens})
        self._vocabulary = {token: index for index, token in enumerate(vocabulary)}
        self._idf = np.zeros(len(vocabulary), dtype="float64")
        self._components = np.zeros((0, len(vocabulary)), dtype="float64")
        self._document_vectors = tuple()
        self._dimension = 0
        if not tokenized or not vocabulary:
            return

        matrix = np.zeros((len(tokenized), len(vocabulary)), dtype="float64")
        document_frequency = np.zeros(len(vocabulary), dtype="float64")
        for row, tokens in enumerate(tokenized):
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            for token, count in counts.items():
                column = self._vocabulary[token]
                matrix[row, column] = math.log1p(count)
                document_frequency[column] += 1.0

        self._idf = np.log((1.0 + len(tokenized)) / (1.0 + document_frequency)) + 1.0
        matrix *= self._idf
        _u, singular_values, components = np.linalg.svd(matrix, full_matrices=False)
        rank = min(dimensions, len(singular_values), len(vocabulary))
        if rank == 0:
            return
        self._components = components[:rank]
        self._dimension = rank
        # U * S is the document embedding in the same space used by queries.
        self._document_vectors = tuple(
            tuple(float(value) for value in row)
            for row in (_u[:, :rank] * singular_values[:rank])
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_query(self, text: str) -> Sequence[float]:
        return self._transform(text)

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return tuple(self._transform(text) for text in texts)

    def document_vectors(self) -> tuple[Sequence[float], ...]:
        """Return vectors fitted from the complete local corpus when available."""

        return self._document_vectors

    def safe_metadata(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "mode": "local",
            "model": "tfidf_lsa",
            "dimensions": self.dimension,
            "external_service": False,
        }

    def _transform(self, text: str) -> tuple[float, ...]:
        if self._dimension == 0:
            return tuple()
        vector = self._np.zeros(len(self._vocabulary), dtype="float64")
        counts: dict[str, int] = {}
        for token in _semantic_tokens(text):
            if token in self._vocabulary:
                counts[token] = counts.get(token, 0) + 1
        for token, count in counts.items():
            vector[self._vocabulary[token]] = math.log1p(count) * self._idf[self._vocabulary[token]]
        projected = vector @ self._components[: self._dimension].T
        return tuple(float(value) for value in projected)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return a safe cosine similarity, including for empty/zero vectors."""

    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


_SEMANTIC_STOP_WORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "could",
    "does",
    "for",
    "from",
    "have",
    "how",
    "into",
    "that",
    "the",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "your",
}


def _semantic_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.lower())
        if token not in _SEMANTIC_STOP_WORDS and (len(token) > 2 or any(char.isdigit() for char in token))
    )
