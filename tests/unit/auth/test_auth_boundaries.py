import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.auth.service import LocalAuthService, hash_password, normalize_username, verify_password


class AuthenticationBoundaryTest(unittest.TestCase):
    def test_expired_session_is_purged_and_cannot_be_reused(self) -> None:
        service = LocalAuthService()
        result = service.login("u001", "nexusone-local-dev")
        assert result.session is not None
        token = result.session.session_token
        service._sessions[token] = replace(
            result.session,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )

        self.assertIsNone(service.current_session(token))
        self.assertNotIn(token, service._sessions)

    def test_malformed_password_verifiers_fail_closed(self) -> None:
        for encoded in ("", "plain-text", "pbkdf2_sha256$not-an-int$salt$digest", "other$1$c2FsdA$ZGlnaWVzdA"):
            with self.subTest(encoded=encoded):
                self.assertFalse(verify_password("password", encoded))
        self.assertFalse(verify_password("password", None))  # type: ignore[arg-type]

    def test_username_normalization_is_bounded_and_non_string_input_is_empty(self) -> None:
        self.assertEqual("u001", normalize_username("  U001 "))
        self.assertEqual("", normalize_username(None))  # type: ignore[arg-type]
        self.assertEqual("", normalize_username(123))  # type: ignore[arg-type]

    def test_password_hash_rejects_empty_input(self) -> None:
        with self.assertRaises(ValueError):
            hash_password("")
        with self.assertRaises(ValueError):
            hash_password(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
