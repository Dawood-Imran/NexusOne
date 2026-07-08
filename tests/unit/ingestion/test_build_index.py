import tempfile
import unittest
from pathlib import Path

from app.ingestion.build_index import build_chunk_records, build_index
from app.ingestion.loaders.documents import load_source_documents


class BuildIndexTest(unittest.TestCase):
    def test_loads_markdown_and_pdf_source_documents(self) -> None:
        documents = load_source_documents()

        source_types = {document.source_type for document in documents}

        self.assertIn("markdown", source_types)
        self.assertIn("pdf", source_types)

    def test_chunks_preserve_permission_metadata(self) -> None:
        documents = load_source_documents()
        records = build_chunk_records(documents)

        executive_chunks = [record for record in records if record.doc_id == "q4-revenue-risk-register-2025"]

        self.assertTrue(executive_chunks)
        self.assertEqual("executive", executive_chunks[0].confidentiality)
        self.assertIn("ceo", executive_chunks[0].allowed_roles)

    def test_build_index_writes_metadata_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            metadata_path = root / "chunks.jsonl"
            faiss_path = root / "chunks.index"
            report_path = root / "report.json"

            report = build_index(metadata_path=metadata_path, faiss_path=faiss_path, report_path=report_path)

            self.assertTrue(metadata_path.exists())
            self.assertTrue(report_path.exists())
            self.assertGreater(report["chunk_count"], 0)
            self.assertIn(report["faiss_status"], {"not_installed", "written", "empty"})


if __name__ == "__main__":
    unittest.main()
