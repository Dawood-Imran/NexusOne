"""Small permission-aware Markdown KB retriever for the Phase 1 app shell."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.auth.profiles import UserProfile


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
    document: KBDocument
    score: int
    snippet: str


class LocalKBRetriever:
    """Permission-aware lexical retriever over generated Markdown KB files."""

    def __init__(self, kb_root: Path = DEFAULT_KB_ROOT) -> None:
        self.kb_root = kb_root
        self.documents = tuple(load_markdown_documents(kb_root))

    def search(self, query: str, profile: UserProfile, max_results: int = 3) -> tuple[RetrievalResult, ...]:
        terms = _tokenize(query)
        if not terms:
            return ()
        results: list[RetrievalResult] = []
        for document in self.documents:
            if not can_access_document(profile, document):
                continue
            haystack = f"{document.title}\n{document.body}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score <= 0:
                continue
            results.append(RetrievalResult(document=document, score=score, snippet=_best_snippet(document.body, terms)))
        results.sort(key=lambda item: (item.score, item.document.updated_at), reverse=True)
        return tuple(results[:max_results])


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
    if profile.status != "active":
        return False
    if profile.user_id in document.allowed_users:
        return True
    if profile.role in document.allowed_roles:
        return True
    return bool(set(profile.groups).intersection(document.allowed_groups))


def build_answer_from_results(query: str, results: tuple[RetrievalResult, ...]) -> str:
    if not results:
        return (
            "I do not have enough accessible source context to answer that confidently. "
            "Try asking about a public policy, an internal process, or your own support tickets."
        )

    top = results[0]
    lines = [f"From {top.document.title}:"]
    snippet = top.snippet.strip()
    if snippet:
        lines.append(snippet)
    if len(results) > 1:
        related = ", ".join(result.document.title for result in results[1:])
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
    return tuple(
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) > 2 and token not in stop_words
    )


def _best_snippet(body: str, terms: tuple[str, ...]) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", body) if paragraph.strip()]
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
