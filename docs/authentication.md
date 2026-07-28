# Local development authentication contract

NexusOne currently uses a **synthetic, process-local authentication service**. It
is not an external identity-provider integration. The service verifies seeded
manifest accounts with salted PBKDF2-HMAC-SHA256 password verifiers and stores
only opaque random session tokens in the server process. Sessions are lost when
the development server stops; a multi-worker or production deployment must
replace the in-memory session store with a shared server-side store.

## Seeded development accounts

The synthetic usernames are the manifest IDs `u001` through `u008`. The
checked-in password verifiers use the intentionally non-production local
fallback `nexusone-local-dev`. Set `NEXUSONE_AUTH_PASSWORD` before starting the
server to provision a different local password for all seeded users. Do not use
this fallback or synthetic accounts outside local development, and do not put a
real credential in source control.

Password text is accepted only by the login request, is verified in memory, and
is never returned, logged, placed in a session, or sent to the orchestrator.
Only password verifiers are retained in account records.

## Session cookie

A successful login returns an opaque cookie:

```http
Set-Cookie: nexusone_session=<random-token>; Path=/; Max-Age=<ttl>; HttpOnly; SameSite=Lax
```

`Secure` is added when `NEXUSONE_AUTH_COOKIE_SECURE=true`; it is off by default
for the local HTTP server. Browsers should send the cookie automatically. The
cookie value is not a signed user payload and must not be decoded by the UI;
the server resolves it to the immutable session identity.

## Endpoints

### `POST /api/auth/login`

Request:

```json
{"username":"u001","password":"<local password>"}
```

Success (`200`) sets the session cookie and returns only safe display details:

```json
{
  "status": "authenticated",
  "user": {
    "user_id": "u001",
    "name": "Ayesha Khan",
    "title": "Software Engineer",
    "role": "employee",
    "department": "engineering",
    "location": "Pakistan",
    "avatar": null
  },
  "expires_at": "2026-01-01T00:00:00+00:00"
}
```

Invalid, missing, or malformed credentials return the same generic response
(`401`) so account existence is not disclosed:

```json
{
  "status": "error",
  "reason_code": "INVALID_CREDENTIALS",
  "message": "Username or password is incorrect."
}
```

### `GET /api/auth/session`

Requires the session cookie. Returns `200` with the same `status`, `user`, and
`expires_at` shape as login. Missing, invalid, or expired cookies return `401`:

```json
{
  "status": "error",
  "reason_code": "AUTHENTICATION_REQUIRED",
  "message": "Sign in before using this endpoint."
}
```

### `POST /api/auth/logout`

Invalidates the server-side session and clears the cookie. Logout is idempotent
and returns `200`:

```json
{"status":"signed_out"}
```

### `POST /api/conversations`

Requires the session cookie. Creates a server-owned conversation and returns its
opaque UUID. A browser must not invent a durable conversation ID.

```json
{
  "status": "created",
  "conversation_id": "2d5c...",
  "title": "New conversation",
  "turn_count": 0
}
```

`GET /api/conversations` lists the authenticated owner's bounded recent
conversations and turns. `GET /api/conversations/{conversation_id}` reads one
owner-scoped conversation. `DELETE /api/conversations/{conversation_id}`
removes it for that owner. Unknown and other-owner IDs return the same generic
`CONVERSATION_NOT_FOUND` response.

### `POST /api/chat`

Requires the session cookie. Request body:

```json
{
  "conversation_id": "2d5c...",
  "turn_id": "optional-client-idempotency-id",
  "message": "How do I request AWS access?",
  "include_trace": false,
  "memory_opt_in": false
}
```

`conversation_id` is optional for compatibility. When omitted, the server
creates a UUID conversation; subsequent turns must send the returned ID. The
response and every SSE event's `response.start`/`response.complete` metadata
return `conversation_id` and a server-generated `turn_id`. A repeated turn ID
with identical text replays the stored response; a different text returns
`TURN_ID_REUSE` (`409`). Malformed IDs return `400`; unknown or other-owner
IDs return `404` without confirming ownership or existence.

The server takes the user ID/profile/role from the session and passes that
identity to the orchestrator. A legacy `user_id` field is ignored as an
authority source; if supplied, it must exactly match the session user ID as a
migration consistency check. A different value returns `403`:

```json
{
  "status": "error",
  "reason_code": "IDENTITY_MISMATCH",
  "message": "The request identity must match the authenticated session."
}
```

Unauthenticated requests return the `AUTHENTICATION_REQUIRED` `401` response
shown above. Chat responses include a safe `profile` object only; email,
groups, account status, password material, and session tokens are not returned.

### `POST /api/feedback`

Requires the session cookie. Request body:

```json
{
  "conversation_id": "web-chat",
  "turn_id": "web-turn",
  "rating": "helpful",
  "comment": "Useful source."
}
```

The feedback repository receives the session user ID. A body `user_id` is
optional only for the same migration consistency check and cannot change the
owner. It receives the same `403 IDENTITY_MISMATCH` response on mismatch and
`401 AUTHENTICATION_REQUIRED` without a session.

There is no authenticated profile list endpoint and no role-switching endpoint.
Role/profile selection is not an authorization mechanism; the server-owned
session is the sole authority.
