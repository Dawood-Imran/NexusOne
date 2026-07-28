"""Validated configuration for permission-aware hybrid retrieval."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class HybridRetrievalConfig:
    """Weights and candidate bounds for lexical + semantic retrieval.

    Scores are combined after normalization, so the weights are relative and
    do not need to add up to one.  Candidate counts control the union of the
    lexical and semantic pools before document-level de-duplication.
    """

    lexical_weight: float = 0.55
    semantic_weight: float = 0.45
    lexical_candidate_count: int = 32
    semantic_candidate_count: int = 32
    max_results: int = 20

    def __post_init__(self) -> None:
        weights = (self.lexical_weight, self.semantic_weight)
        if any(not math.isfinite(weight) or weight < 0 for weight in weights):
            raise ValueError("retrieval weights must be finite and non-negative")
        if sum(weights) <= 0:
            raise ValueError("at least one retrieval weight must be greater than zero")
        for name, value in (
            ("lexical_candidate_count", self.lexical_candidate_count),
            ("semantic_candidate_count", self.semantic_candidate_count),
            ("max_results", self.max_results),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_results > 1000:
            raise ValueError("max_results must not exceed 1000")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "HybridRetrievalConfig":
        """Read explicit retrieval settings and fail closed on invalid values."""

        values = os.environ if environ is None else environ
        return cls(
            lexical_weight=_float_value(values, "NEXUSONE_RETRIEVAL_LEXICAL_WEIGHT", 0.55),
            semantic_weight=_float_value(values, "NEXUSONE_RETRIEVAL_SEMANTIC_WEIGHT", 0.45),
            lexical_candidate_count=_int_value(values, "NEXUSONE_RETRIEVAL_LEXICAL_CANDIDATES", 32),
            semantic_candidate_count=_int_value(values, "NEXUSONE_RETRIEVAL_SEMANTIC_CANDIDATES", 32),
            max_results=_int_value(values, "NEXUSONE_RETRIEVAL_MAX_RESULTS", 20),
        )

    def safe_metadata(self) -> dict[str, object]:
        """Return non-secret settings suitable for a capability response."""

        return {
            "lexical_weight": self.lexical_weight,
            "semantic_weight": self.semantic_weight,
            "lexical_candidate_count": self.lexical_candidate_count,
            "semantic_candidate_count": self.semantic_candidate_count,
            "max_results": self.max_results,
            "score_normalization": "lexical_max_and_positive_cosine",
            "tie_breaking": "score_then_lexical_then_semantic_then_doc_id_then_chunk_index",
        }


def _float_value(values: Mapping[str, str], name: str, default: float) -> float:
    raw = values.get(name)
    if raw is None:
        return default
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{name} must be a finite number")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc


def _int_value(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name)
    if raw is None:
        return default
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{name} must be a positive integer")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
