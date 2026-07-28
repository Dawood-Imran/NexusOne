"""Build permission-carrying RAG chunk metadata and optional FAISS index."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from app.ingestion.chunking.text import chunk_text
from app.ingestion.loaders.documents import SourceDocument, load_source_documents


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA_PATH = ROOT / "data" / "faiss" / "nexusone_chunks_metadata.jsonl"
DEFAULT_FAISS_PATH = ROOT / "data" / "faiss" / "nexusone_chunks.index"
DEFAULT_REPORT_PATH = ROOT / "data" / "generated" / "ingestion_reports" / "rag_index_report.json"


@dataclass(frozen=True)
class ChunkRecord:
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


def build_chunk_records(documents: tuple[SourceDocument, ...]) -> tuple[ChunkRecord, ...]:
    records: list[ChunkRecord] = []
    for document in documents:
        chunks = chunk_text(document.body)
        for index, chunk in enumerate(chunks):
            records.append(
                ChunkRecord(
                    chunk_id=f"{document.doc_id}:{index}",
                    doc_id=document.doc_id,
                    chunk_index=index,
                    title=document.title,
                    source_type=document.source_type,
                    source_path=document.source_path,
                    department=document.department,
                    confidentiality=document.confidentiality,
                    allowed_roles=document.allowed_roles,
                    allowed_groups=document.allowed_groups,
                    allowed_users=document.allowed_users,
                    updated_at=document.updated_at,
                    text=chunk,
                    token_estimate=max(1, math.ceil(len(chunk.split()) * 1.25)),
                )
            )
    return tuple(records)


def write_metadata(records: tuple[ChunkRecord, ...], metadata_path: Path = DEFAULT_METADATA_PATH) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = asdict(record)
            payload["allowed_roles"] = list(record.allowed_roles)
            payload["allowed_groups"] = list(record.allowed_groups)
            payload["allowed_users"] = list(record.allowed_users)
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def build_optional_faiss(records: tuple[ChunkRecord, ...], faiss_path: Path = DEFAULT_FAISS_PATH) -> str:
    """Write an optional FAISS index over local LSA vectors.

    The function name is retained for CLI/report compatibility.  It no longer
    writes the removed token-hash vectors.  The metadata retriever can operate
    without FAISS and computes the same local semantic space directly, which
    keeps default tests and local development credential-free.
    """

    try:
        import faiss  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        return "not_installed"

    if not records:
        return "empty"
    try:
        from app.retrieval.embeddings import LocalSemanticEmbeddingProvider

        provider = LocalSemanticEmbeddingProvider(tuple(record.text for record in records))
        vectors = np.array(provider.embed_documents([record.text for record in records]), dtype="float32")
    except Exception:
        return "semantic_unavailable"
    if vectors.ndim != 2 or vectors.shape[0] != len(records) or vectors.shape[1] == 0:
        return "semantic_unavailable"
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(faiss_path))
    return "written"


def write_report(
    documents: tuple[SourceDocument, ...],
    records: tuple[ChunkRecord, ...],
    faiss_status: str,
    report_path: Path = DEFAULT_REPORT_PATH,
    *,
    metadata_path: Path = DEFAULT_METADATA_PATH,
    faiss_path: Path = DEFAULT_FAISS_PATH,
) -> dict[str, object]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    by_confidentiality = Counter(record.confidentiality for record in records)
    by_source_type = Counter(record.source_type for record in records)
    report = {
        "document_count": len(documents),
        "chunk_count": len(records),
        "metadata_path": _report_path(metadata_path),
        "faiss_path": _report_path(faiss_path),
        "faiss_status": faiss_status,
        "embedding_provider": "local_lsa" if records else "not_available",
        "chunks_by_confidentiality": dict(sorted(by_confidentiality.items())),
        "chunks_by_source_type": dict(sorted(by_source_type.items())),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _report_path(path: Path) -> str:
    """Keep committed reports portable across worktrees."""

    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def build_index(
    metadata_path: Path = DEFAULT_METADATA_PATH,
    faiss_path: Path = DEFAULT_FAISS_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> dict[str, object]:
    documents = load_source_documents()
    records = build_chunk_records(documents)
    write_metadata(records, metadata_path)
    faiss_status = build_optional_faiss(records, faiss_path)
    return write_report(
        documents,
        records,
        faiss_status,
        report_path,
        metadata_path=metadata_path,
        faiss_path=faiss_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build NexusOne RAG chunk metadata and optional FAISS index.")
    parser.add_argument("--metadata-path", default=str(DEFAULT_METADATA_PATH))
    parser.add_argument("--faiss-path", default=str(DEFAULT_FAISS_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = build_index(
        metadata_path=Path(args.metadata_path),
        faiss_path=Path(args.faiss_path),
        report_path=Path(args.report_path),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
