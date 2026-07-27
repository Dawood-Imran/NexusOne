"""Local-only username/password authentication and server-owned sessions.

This module intentionally does not integrate with an external identity provider.
Synthetic account password material is stored as salted PBKDF2-HMAC-SHA256
verifiers.  Successful authentication creates an opaque, random session token
that is retained only in the process-local session store; the token is sent to
browsers as an HttpOnly cookie by the HTTP adapter.

The HTTP contract is documented in ``docs/authentication.md``.  In particular,
callers must resolve identity from :class:`AuthenticatedSession`, never from a
request-body ``user_id``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Mapping

from app.auth.profiles import PROFILES, UserProfile, get_profile


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
# Kept at a practical local-development cost for this repository's stdlib
# server.  Passwords are still salted and verified with a deliberately slow KDF.
PASSWORD_HASH_ITERATIONS = 100_000
PASSWORD_SALT_BYTES = 16
SESSION_TOKEN_BYTES = 32
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60
DEFAULT_LOCAL_PASSWORD_ENV = "NEXUSONE_AUTH_PASSWORD"


@dataclass(frozen=True)
class AuthAccount:
    """Stored account record.  ``password_hash`` is deliberately not exposed."""

    username: str
    user_id: str
    password_hash: str = field(repr=False)
    enabled: bool = True


@dataclass(frozen=True)
class AuthenticatedSession:
    """Server-owned identity associated with one authenticated session."""

    user_id: str
    profile: UserProfile
    created_at: datetime
    expires_at: datetime
    session_token: str = field(repr=False)

    @property
    def safe_user(self) -> dict[str, object]:
        return self.profile.to_public_dict()


@dataclass(frozen=True)
class LoginResult:
    authenticated: bool
    session: AuthenticatedSession | None = None
    reason_code: str | None = None


# These are salted verifiers for the intentionally synthetic local fallback
# credential.  They are not production credentials.  Set NEXUSONE_AUTH_PASSWORD
# in a local environment to provision a different local password for the seed users.
# The plaintext fallback is never kept in this module or returned by the API.
_SEEDED_PASSWORD_HASHES: dict[str, str] = {
    "u001": "pbkdf2_sha256$100000$_17YgC9DYY7IHe8wNxaKkg$JkXzShCh0xuXreszPQTmz5dHMENtY43Yu7j-arfT1wA",
    "u002": "pbkdf2_sha256$100000$qPPg0MfUq8Bd0tyiUXPehg$pSmsWhRfoEXbH0O6_MJ8GFAV-7Z_50paY7jlbWBYcII",
    "u003": "pbkdf2_sha256$100000$-k7tv9qiWlnDja9Yg1tp9A$gAdrrqH5raJeCotcl5dRz4hjwjrIX17GIFbEr4NJiPQ",
    "u004": "pbkdf2_sha256$100000$Hwk6Bk7U3Vh718iC-sx8Dw$_4z4M4o6J9qlmG_SKw58l066kutPkjVOwQjmarvYonQ",
    "u005": "pbkdf2_sha256$100000$9iKfDPi71C5rgR0EAsrzYA$bjdX5xie93RJVc8OOKoOElWg1llPqxy8a1hVt4yMz3g",
    "u006": "pbkdf2_sha256$100000$iKrtfKpuu6SDvEIYMpLA8A$0FmkfZWkNe45v24bpx3HT9XYRajxfF4fAMcta22HgsM",
    "u007": "pbkdf2_sha256$100000$YObskpOTZGWY3p7XoUD5UA$jplwfQ7M9qcTg7J9Xs2tGDGXGIhrjEfB9ZBFie8xT8Y",
    "u008": "pbkdf2_sha256$100000$1Y_ldwuw-tWCR1-xfltSaA$a6-7XLc2hM8aymAe9hvpbVqXXWCy25IKTMKnUbcV5bs",
}


def hash_password(password: str) -> str:
    """Return a salted password verifier; never return the input password."""

    if not isinstance(password, str) or not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    digest = _derive_password(password, salt, PASSWORD_HASH_ITERATIONS)
    return _format_hash(salt, digest, PASSWORD_HASH_ITERATIONS)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Constant-time verification for a stored PBKDF2 password verifier."""

    try:
        algorithm, iterations_text, salt_text, digest_text = encoded_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _decode(salt_text)
        expected = _decode(digest_text)
        if iterations <= 0 or not salt or not expected:
            return False
        actual = _derive_password(password, salt, iterations)
    except (TypeError, ValueError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


class LocalAuthService:
    """Authenticate seeded synthetic users and own an in-memory session store.

    The service is intentionally process-local for the repository's development
    server.  Sessions disappear when the process stops; deployments must replace
    this store with a shared server-side store before using multiple workers.
    """

    def __init__(
        self,
        accounts: Mapping[str, AuthAccount] | None = None,
        *,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> None:
        if session_ttl_seconds <= 0:
            raise ValueError("session_ttl_seconds must be positive")
        supplied_accounts = build_seeded_accounts() if accounts is None else accounts
        self.accounts = {
            normalize_username(username): account for username, account in supplied_accounts.items()
        }
        self.session_ttl_seconds = session_ttl_seconds
        self._sessions: dict[str, AuthenticatedSession] = {}
        self._lock = threading.RLock()

    def login(self, username: str, password: str) -> LoginResult:
        """Verify credentials and issue a new opaque random session token."""

        normalized_username = normalize_username(username)
        with self._lock:
            account = self.accounts.get(normalized_username)
            # Verify against a real stored verifier even for an unknown username
            # so the common failure path does not reveal account existence.
            stored_hash = account.password_hash if account is not None else self._dummy_hash()
            password_matches = verify_password(password, stored_hash)
            if account is None or not account.enabled or not password_matches:
                return LoginResult(authenticated=False, reason_code="INVALID_CREDENTIALS")

            profile = get_profile(account.user_id)
            if profile is None or profile.status != "active":
                return LoginResult(authenticated=False, reason_code="INVALID_CREDENTIALS")

            now = datetime.now(UTC)
            session = AuthenticatedSession(
                user_id=account.user_id,
                profile=profile,
                created_at=now,
                expires_at=now + timedelta(seconds=self.session_ttl_seconds),
                session_token=secrets.token_urlsafe(SESSION_TOKEN_BYTES),
            )
            self._purge_expired(now)
            self._sessions[session.session_token] = session
            return LoginResult(authenticated=True, session=session)

    def current_session(self, session_token: str | None) -> AuthenticatedSession | None:
        """Resolve a cookie token to its immutable server-side identity."""

        if not session_token:
            return None
        with self._lock:
            session = self._sessions.get(session_token)
            if session is None:
                return None
            if session.expires_at <= datetime.now(UTC):
                self._sessions.pop(session_token, None)
                return None
            return session

    def logout(self, session_token: str | None) -> None:
        """Invalidate a session token; missing/unknown tokens are harmless."""

        if not session_token:
            return
        with self._lock:
            self._sessions.pop(session_token, None)

    def _dummy_hash(self) -> str:
        if self.accounts:
            return next(iter(self.accounts.values())).password_hash
        # No accounts is a configuration error, but preserve a safe failure path.
        return hash_password(secrets.token_urlsafe(32))

    def _purge_expired(self, now: datetime) -> None:
        expired = [token for token, session in self._sessions.items() if session.expires_at <= now]
        for token in expired:
            self._sessions.pop(token, None)


def build_seeded_accounts(password: str | None = None) -> dict[str, AuthAccount]:
    """Build username-to-account records for the synthetic manifest users.

    Usernames intentionally use the manifest ``user_id`` values (``u001`` …)
    so this local service does not expose or depend on employee email addresses.
    A configured ``NEXUSONE_AUTH_PASSWORD`` replaces the checked-in synthetic
    fallback verifiers at process start and is never returned or logged.
    """

    configured_password = password
    if configured_password is None:
        configured_password = os.getenv(DEFAULT_LOCAL_PASSWORD_ENV)
    configured_hash = hash_password(configured_password) if configured_password else None
    accounts: dict[str, AuthAccount] = {}
    for user_id, profile in PROFILES.items():
        password_hash = configured_hash or _SEEDED_PASSWORD_HASHES.get(user_id)
        if not password_hash:
            continue
        accounts[user_id] = AuthAccount(
            username=user_id,
            user_id=user_id,
            password_hash=password_hash,
            enabled=profile.status == "active",
        )
    return accounts


def normalize_username(username: str) -> str:
    if not isinstance(username, str):
        return ""
    return username.strip().casefold()


def _derive_password(password: str, salt: bytes, iterations: int) -> bytes:
    if not isinstance(password, str):
        return b""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )


def _format_hash(salt: bytes, digest: bytes, iterations: int) -> str:
    return "$".join(
        (
            PASSWORD_HASH_ALGORITHM,
            str(iterations),
            _encode(salt),
            _encode(digest),
        )
    )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


# Short alias keeps imports pleasant for the small local API adapter.
AuthService = LocalAuthService

__all__ = [
    "AuthAccount",
    "AuthService",
    "AuthenticatedSession",
    "LocalAuthService",
    "LoginResult",
    "build_seeded_accounts",
    "hash_password",
    "normalize_username",
    "verify_password",
]
