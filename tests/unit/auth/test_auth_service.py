import unittest
from datetime import UTC, datetime

from app.auth.service import (
    AuthAccount,
    LocalAuthService,
    hash_password,
    verify_password,
)


class LocalAuthServiceTest(unittest.TestCase):
    def test_password_is_stored_as_salted_verifier(self) -> None:
        first = hash_password("test-password")
        second = hash_password("test-password")

        self.assertNotEqual(first, second)
        self.assertNotIn("test-password", first)
        self.assertTrue(verify_password("test-password", first))
        self.assertFalse(verify_password("wrong-password", first))

    def test_valid_login_returns_immutable_safe_session(self) -> None:
        service = LocalAuthService(session_ttl_seconds=60)

        result = service.login(" U001 ", "nexusone-local-dev")

        self.assertTrue(result.authenticated)
        self.assertIsNotNone(result.session)
        assert result.session is not None
        self.assertEqual("u001", result.session.user_id)
        self.assertEqual("employee", result.session.profile.role)
        self.assertEqual(
            {
                "user_id": "u001",
                "name": "Ayesha Khan",
                "title": "Software Engineer",
                "role": "employee",
                "department": "engineering",
                "location": "Pakistan",
                "avatar": None,
            },
            result.session.safe_user,
        )
        self.assertNotIn("password", repr(result.session).lower())
        self.assertGreater(result.session.expires_at, datetime.now(UTC))

    def test_invalid_credentials_do_not_create_a_session(self) -> None:
        service = LocalAuthService()

        result = service.login("u001", "wrong-password")
        unknown = service.login("missing", "wrong-password")

        self.assertFalse(result.authenticated)
        self.assertEqual("INVALID_CREDENTIALS", result.reason_code)
        self.assertFalse(unknown.authenticated)
        self.assertEqual("INVALID_CREDENTIALS", unknown.reason_code)
        self.assertIsNone(service.current_session(None))

    def test_session_persists_until_logout(self) -> None:
        service = LocalAuthService()
        result = service.login("u001", "nexusone-local-dev")
        assert result.session is not None

        self.assertIs(service.current_session(result.session.session_token), result.session)
        service.logout(result.session.session_token)
        self.assertIsNone(service.current_session(result.session.session_token))

    def test_disabled_account_cannot_login(self) -> None:
        account = AuthAccount(
            username="u001",
            user_id="u001",
            password_hash=hash_password("test-password"),
            enabled=False,
        )
        service = LocalAuthService({"u001": account})

        result = service.login("u001", "test-password")

        self.assertFalse(result.authenticated)
        self.assertEqual("INVALID_CREDENTIALS", result.reason_code)


if __name__ == "__main__":
    unittest.main()
