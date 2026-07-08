import unittest

from app.auth.profiles import get_profile
from app.retrieval.local_kb import LocalKBRetriever


class LocalKBRetrieverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.retriever = LocalKBRetriever()

    def test_employee_can_retrieve_aws_access_from_allowed_group(self) -> None:
        profile = get_profile("u001")
        assert profile is not None

        results = self.retriever.search("How do I request AWS access?", profile)

        titles = {result.document.title for result in results}
        self.assertIn("AWS Access Request", titles)

    def test_employee_does_not_retrieve_executive_strategy(self) -> None:
        profile = get_profile("u001")
        assert profile is not None

        results = self.retriever.search("strategic priorities acquisition opportunity", profile, max_results=10)

        self.assertFalse(any(result.document.confidentiality in {"executive", "ceo_only"} for result in results))

    def test_ceo_can_retrieve_executive_material(self) -> None:
        profile = get_profile("u006")
        assert profile is not None

        results = self.retriever.search("strategic priorities acquisition opportunity", profile, max_results=10)

        self.assertTrue(any(result.document.confidentiality in {"executive", "ceo_only"} for result in results))


if __name__ == "__main__":
    unittest.main()
