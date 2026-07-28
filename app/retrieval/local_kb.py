"""Small permission-aware Markdown KB retriever for the Phase 1 app shell."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from app.auth.profiles import UserProfile
from app.retrieval.access import can_access_metadata
from app.retrieval.config import NO_REFERENCE_MESSAGE, SOURCE_SIMILARITY_THRESHOLD


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_ROOT = ROOT / "data" / "docs" / "markdown_kb"


@dataclass(frozen=True)
class Citation:
    doc_id: str
    title: str
    source_type: str
    source_path: str
    updated_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class KBDocument:
    doc_id: str
    title: str
    source_type: str
    source_path: str
    department: str
    confidentiality: str
    allowed_roles: tuple[str, ...]
    allowed_groups: tuple[str, ...]
    allowed_users: tuple[str, ...]
    updated_at: str
    body: str

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
class RetrievalResult:
    """A retained lexical fallback source on the public 0-100 score scale."""

    document: KBDocument
    score: float
    snippet: str


class LocalKBRetriever:
    """Permission-aware lexical fallback with the shared relevance policy."""

    def __init__(
        self,
        kb_root: Path = DEFAULT_KB_ROOT,
        *,
        similarity_threshold: float = SOURCE_SIMILARITY_THRESHOLD,
    ) -> None:
        if not math.isfinite(similarity_threshold) or not 0.0 <= similarity_threshold <= 100.0:
            raise ValueError("similarity_threshold must be between 0 and 100")
        self.kb_root = kb_root
        self.similarity_threshold = similarity_threshold
        self.documents = tuple(load_markdown_documents(kb_root))

    def search(self, query: str, profile: UserProfile, max_results: int = 3) -> tuple[RetrievalResult, ...]:
        terms = _tokenize(query)
        if not terms or max_results <= 0:
            return ()
        accessible = [document for document in self.documents if can_access_document(profile, document)]
        raw_scores = {
            document.doc_id: float(sum(f"{document.title}\n{document.body}".lower().count(term) for term in terms))
            for document in accessible
        }
        maximum = max(raw_scores.values(), default=0.0)
        if maximum <= 0.0:
            return ()
        results: list[RetrievalResult] = []
        for document in accessible:
            normalized_score = 100.0 * raw_scores[document.doc_id] / maximum
            if normalized_score < self.similarity_threshold:
                continue
            results.append(
                RetrievalResult(
                    document=document,
                    score=normalized_score,
                    snippet=_best_snippet(document.body, terms),
                )
            )
        results.sort(key=lambda item: (-item.score, item.document.doc_id, item.document.updated_at))
        return tuple(_dedupe_documents(results)[:max_results])


def load_markdown_documents(kb_root: Path = DEFAULT_KB_ROOT) -> list[KBDocument]:
    documents: list[KBDocument] = []
    if not kb_root.exists():
        return documents
    for path in sorted(kb_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_front_matter(text)
        if not metadata:
            continue
        documents.append(
            KBDocument(
                doc_id=metadata.get("doc_id", path.stem),
                title=metadata.get("title", path.stem.replace("-", " ").title()),
                source_type=metadata.get("source_type", "markdown"),
                source_path=metadata.get("source_path", str(path)),
                department=metadata.get("department", ""),
                confidentiality=metadata.get("confidentiality", "public_internal"),
                allowed_roles=_parse_inline_list(metadata.get("allowed_roles", "")),
                allowed_groups=_parse_inline_list(metadata.get("allowed_groups", "")),
                allowed_users=_parse_inline_list(metadata.get("allowed_users", "")),
                updated_at=metadata.get("updated_at", ""),
                body=body.strip(),
            )
        )
    return documents


def can_access_document(profile: UserProfile, document: KBDocument) -> bool:
    return can_access_metadata(
        profile,
        department=document.department,
        confidentiality=document.confidentiality,
        allowed_roles=document.allowed_roles,
        allowed_groups=document.allowed_groups,
        allowed_users=document.allowed_users,
    )


def build_answer_from_results(
    query: str,
    results: tuple[RetrievalResult, ...],
    *,
    threshold: float = SOURCE_SIMILARITY_THRESHOLD,
) -> str:
    retained = tuple(result for result in results if result.score >= threshold)
    if not retained:
        return NO_REFERENCE_MESSAGE

    top = retained[0]
    lines = [f"From {top.document.title}:"]
    snippet = top.snippet.strip()
    if snippet:
        lines.append(snippet)
    if len(retained) > 1:
        related = ", ".join(result.document.title for result in retained[1:])
        lines.append(f"Related accessible sources: {related}.")
    return "\n\n".join(lines)


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    raw_meta = parts[1]
    body = parts[2]
    metadata: dict[str, str] = {}
    for raw_line in raw_meta.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, body


def _parse_inline_list(value: str) -> tuple[str, ...]:
    stripped = value.strip()
    if not stripped or stripped == "[]":
        return ()
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1]
    return tuple(item.strip().strip("'\"") for item in stripped.split(",") if item.strip())


def _tokenize(query: str) -> tuple[str, ...]:
    """Tokenize useful terms without discarding identifiers or acronyms."""

    stop_words = {
        "about",
        "can",
        "could",
        "does",
        "for",
        "from",
        "have",
        "how",
        "tell",
        "that",
        "the",
        "this",
        "what",
        "when",
        "where",
        "with",
        "your",
    }
    tokens: list[str] = []
    for original_token in re.findall(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", query):
        raw_token = original_token.lower()
        if raw_token in stop_words:
            continue
        # Keep short identifiers/acronyms such as HR, IT, SSO, and ID-7 while
        # retaining the existing stop-word and very-short-token filtering.
        if (
            len(raw_token) > 2
            or (original_token.isupper() and len(raw_token) >= 2)
            or any(char.isdigit() for char in raw_token)
            or "-" in raw_token
            or "_" in raw_token
        ):
            tokens.append(raw_token)
    return tuple(tokens)


def _dedupe_documents(results: list[RetrievalResult]) -> list[RetrievalResult]:
    seen: set[str] = set()
    deduped: list[RetrievalResult] = []
    for result in results:
        if result.document.doc_id in seen:
            continue
        seen.add(result.document.doc_id)
        deduped.append(result)
    return deduped


_SOURCE_INSTRUCTION_PATTERN = re.compile(
    r"(?:ignore|disregard|override|bypass)\s+(?:all\s+|previous\s+|the\s+)?"
    r"(?:instructions?|rules?|guardrails?)|"
    r"(?:reveal|dump|expose)\s+(?:the\s+)?(?:hidden|secret|system|private)",
    re.IGNORECASE,
)


def _best_snippet(body: str, terms: tuple[str, ...]) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", body)
        if paragraph.strip() and not _SOURCE_INSTRUCTION_PATTERN.search(paragraph)
    ]
    if not paragraphs:
        return ""
    scored: list[tuple[int, str]] = []
    for paragraph in paragraphs:
        lowered = paragraph.lower()
        score = sum(lowered.count(term) for term in terms)
        scored.append((score, paragraph))
    scored.sort(key=lambda item: item[0], reverse=True)
    snippet = scored[0][1] if scored[0][0] > 0 else paragraphs[0]
    return _clean_markdown_snippet(snippet)


def _clean_markdown_snippet(snippet: str) -> str:
    cleaned = re.sub(r"^#+\s*", "", snippet, flags=re.MULTILINE)
    cleaned = cleaned.replace("`", "")
    return cleaned.strip()
