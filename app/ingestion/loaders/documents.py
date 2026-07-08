"""Load generated Markdown and PDF-source documents with permission metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.retrieval.local_kb import _parse_front_matter, _parse_inline_list


ROOT = Path(__file__).resolve().parents[3]
MARKDOWN_ROOT = ROOT / "data" / "docs" / "markdown_kb"
PDF_SOURCE_ROOT = ROOT / "data" / "generated" / "pdf_sources"


@dataclass(frozen=True)
class SourceDocument:
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


def load_source_documents(
    markdown_root: Path = MARKDOWN_ROOT,
    pdf_source_root: Path = PDF_SOURCE_ROOT,
) -> tuple[SourceDocument, ...]:
    documents: list[SourceDocument] = []
    for root in (markdown_root, pdf_source_root):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            document = load_source_document(path)
            if document is not None:
                documents.append(document)
    return tuple(documents)


def load_source_document(path: Path) -> SourceDocument | None:
    text = path.read_text(encoding="utf-8")
    metadata, body = _parse_front_matter(text)
    if not metadata:
        return None
    return SourceDocument(
        doc_id=metadata.get("doc_id", path.stem),
        title=metadata.get("title", path.stem.replace("_", " ").replace("-", " ").title()),
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
