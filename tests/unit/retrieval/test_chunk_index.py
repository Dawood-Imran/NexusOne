import unittest

from app.auth.profiles import get_profile
from app.retrieval.chunk_index import MetadataChunkRetriever


class ChunkIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.retriever = MetadataChunkRetriever()

    def test_metadata_index_is_available_after_build(self) -> None:
        self.assertTrue(self.retriever.available())

    def test_employee_cannot_retrieve_executive_revenue_risk_chunk(self) -> None:
        profile = get_profile("u001")
        assert profile is not None

        results = self.retriever.search("Q4 revenue risk register customer risk", profile, max_results=10)

        self.assertFalse(any(result.chunk.doc_id == "q4-revenue-risk-register-2025" for result in results))

    def test_ceo_can_retrieve_executive_revenue_risk_chunk(self) -> None:
        profile = get_profile("u006")
        assert profile is not None

        results = self.retriever.search("Q4 revenue risk register customer risk", profile, max_results=10)

        self.assertTrue(any(result.chunk.doc_id == "q4-revenue-risk-register-2025" for result in results))


if __name__ == "__main__":
    unittest.main()
