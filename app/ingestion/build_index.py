"""Build permission-carrying RAG chunk metadata and optional FAISS index."""

from __future__ import annotations

import argparse
import hashlib
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
    try:
        import faiss  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        return "not_installed"

    if not records:
        return "empty"
    vectors = np.array([_hash_embedding(record.text) for record in records], dtype="float32")
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
) -> dict[str, object]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    by_confidentiality = Counter(record.confidentiality for record in records)
    by_source_type = Counter(record.source_type for record in records)
    report = {
        "document_count": len(documents),
        "chunk_count": len(records),
        "metadata_path": str(DEFAULT_METADATA_PATH),
        "faiss_path": str(DEFAULT_FAISS_PATH),
        "faiss_status": faiss_status,
        "chunks_by_confidentiality": dict(sorted(by_confidentiality.items())),
        "chunks_by_source_type": dict(sorted(by_source_type.items())),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def build_index(
    metadata_path: Path = DEFAULT_METADATA_PATH,
    faiss_path: Path = DEFAULT_FAISS_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> dict[str, object]:
    documents = load_source_documents()
    records = build_chunk_records(documents)
    write_metadata(records, metadata_path)
    faiss_status = build_optional_faiss(records, faiss_path)
    return write_report(documents, records, faiss_status, report_path)


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


def _hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    tokens = text.lower().split()
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


if __name__ == "__main__":
    raise SystemExit(main())
