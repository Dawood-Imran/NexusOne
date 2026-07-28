import unittest

from app.auth.profiles import get_profile
from app.retrieval.chunk_index import Chunk, can_access_chunk
from app.retrieval.local_kb import KBDocument, can_access_document


class RetrievalPermissionBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        profile = get_profile("u001")
        assert profile is not None
        self.profile = profile

    def test_document_access_defaults_deny_when_no_role_group_or_user_matches(self) -> None:
        document = KBDocument(
            doc_id="fixture-restricted",
            title="Restricted fixture",
            source_type="markdown",
            source_path="fixture.md",
            department="finance",
            confidentiality="finance_sensitive",
            allowed_roles=("finance",),
            allowed_groups=("finance_team",),
            allowed_users=(),
            updated_at="2026-01-01",
            body="secret fixture",
        )

        self.assertFalse(can_access_document(self.profile, document))

    def test_document_access_allows_explicit_user_but_inactive_profile_is_denied(self) -> None:
        document = KBDocument(
            doc_id="fixture-user",
            title="User fixture",
            source_type="markdown",
            source_path="fixture.md",
            department="engineering",
            confidentiality="department_internal",
            allowed_roles=(),
            allowed_groups=(),
            allowed_users=("u001",),
            updated_at="2026-01-01",
            body="private fixture",
        )

        self.assertTrue(can_access_document(self.profile, document))
        inactive = self.profile.__class__(**{**self.profile.__dict__, "status": "inactive"})
        self.assertFalse(can_access_document(inactive, document))

    def test_chunk_filter_has_the_same_default_deny_behavior(self) -> None:
        chunk = Chunk(
            chunk_id="fixture:0",
            doc_id="fixture",
            chunk_index=0,
            title="Finance fixture",
            source_type="markdown",
            source_path="fixture.md",
            department="finance",
            confidentiality="finance_sensitive",
            allowed_roles=("finance",),
            allowed_groups=("finance_team",),
            allowed_users=(),
            updated_at="2026-01-01",
            text="hidden amount",
            token_estimate=2,
        )

        self.assertFalse(can_access_chunk(self.profile, chunk))


if __name__ == "__main__":
    unittest.main()
