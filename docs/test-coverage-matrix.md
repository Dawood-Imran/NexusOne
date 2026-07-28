# NexusOne test and evaluation coverage

This is the maintained coverage contract for the local-only product. It is a
risk matrix, not a claim of mathematical or line coverage. The default command
is deterministic and does not require Postgres, OpenAI, LangSmith, production
credentials, or a browser service.

## Baseline inventory

The test/evaluation work started from the reachable checkout at commit
`fed93e9` (`feat: stream copilot responses over SSE`). No streaming code was
merged or changed by this branch. The checkout already contains
`app/api/streaming.py`, the SSE path in `app/api/dev_server.py`, and streaming
unit/HTTP contracts in `tests/unit/api/test_streaming.py`; therefore streaming
coverage is included in this matrix. If this branch is applied to a baseline
before that commit, treat the streaming rows as pending until the streaming
branch lands.

The application is a framework-independent Python service with a stdlib local
HTTP server and static frontend. There is no `package.json`, npm test runner,
production FastAPI adapter, or committed Playwright harness in this checkout.

## Commands

```bash
# Full deterministic unit/integration suite (local process only)
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py'

# Offline model-quality evaluation; no network or provider calls
./.venv/bin/python scripts/run_evaluation.py

# Bounded machine-readable evaluation report
./.venv/bin/python scripts/run_evaluation.py --json

# Python and static JavaScript syntax checks
./.venv/bin/python -m compileall -q app tests scripts
node --check frontend/static/app.js

git diff --check
```

`python3 -m unittest ...` may be environment-limited if the system Python
lacks the packages in `requirements.txt`; use the repository `.venv` for the
supported default command. `npm run lint`, `npm run typecheck`, `npm run
build`, and `npm run test:e2e` are intentionally not listed because those
scripts do not exist here.

Live-provider evaluation is a separate, opt-in contract only:

```bash
# Refuses unless both the explicit flag and a non-placeholder key exist.
./.venv/bin/python scripts/run_live_evaluation.py
```

The future provider runner is injected into
`tests.evaluation.evaluator.run_live_evaluation`. Authorization, route, and
no-leakage checks remain deterministic; an LLM judge can add quality signal
only and cannot override those checks. Reports contain case ids and bounded
dimension reasons, never prompts, credentials, or raw model answers.

## Matrix

| Surface / risk | Main implementation | Evidence in this branch | Default status | Intentionally not covered |
|---|---|---|---|---|
| Password hashing, normalization, disabled/expired sessions, logout | `app/auth/service.py` | `tests/unit/auth/test_auth_service.py`, `tests/unit/auth/test_auth_boundaries.py` | Covered | Distributed session store and production identity provider |
| HTTP auth/session ownership and impersonation | `app/api/dev_server.py` | `tests/unit/api/test_dev_server_auth.py`, `tests/unit/api/test_local_http_surface.py` | Covered | TLS, reverse proxy cookie policy, multi-worker deployment |
| HTTP malformed input, unknown routes, safe errors | `app/api/dev_server.py` | `tests/unit/api/test_local_http_surface.py` | Covered | Network load/slow-client behavior |
| Guardrails/default deny and prompt injection | `app/guardrails/policy.py`, orchestrator precheck | `tests/unit/services/test_guardrail_policy.py`, `tests/unit/services/test_guardrail_matrix.py`, graph tests, evaluation cases | Covered | Adversarial language beyond the reviewed phrase set |
| Deterministic routing: RAG, SQL, combined, ticket, casual, general, deny/error | `app/agents/orchestrator/routing.py`, graph | `tests/unit/agents/orchestrator/test_graph.py`, `tests/unit/agents/orchestrator/test_routing_contract.py`, evaluation cases | Covered | Statistical classifier quality (there is no statistical classifier) |
| Markdown/chunk retrieval, citations, role/group/user filtering | `app/retrieval/*` | existing retrieval tests plus `tests/unit/retrieval/test_permission_boundaries.py`, graph/evaluation cases | Covered | Fresh ingestion from every PDF/FAISS binary on every test run |
| SQL source allowlist and role scope | `schema_registry.py`, `permissions.py` | `tests/unit/agents/sql_subgraph/test_scope_selection.py`, independent graph tests, guardrail matrix | Covered | Live Postgres permission views in the default command |
| SQL safety validation/repair/limits | `sql_validator.py`, SQL graph | `test_sql_validator.py`, `test_graph_independent.py`, `test_execution_boundaries.py` | Covered | SQL parser/database-specific edge cases not represented by the validator's bounded rules |
| SQL execution and safe presentation | `db.py`, `presentation.py`, parent graph | `test_presentation.py`, `test_execution_boundaries.py`, `tests/unit/services/test_chat_service.py`, HTTP/evaluation cases | Covered with fakes | Postgres transaction/statement-timeout integration |
| Ticket creation/clarification/sanitization | `app/actions/ticket_service.py`, action route | `test_ticket_service.py`, graph tests, local HTTP ticket path, evaluation cases | Covered | Idempotency-key semantics for a retried side-effecting ticket request |
| Feedback and audit metadata | `feedback_service.py`, `audit_service.py`, ChatService | existing action tests, local HTTP feedback retry, ChatService tests | Covered | Postgres schema/constraint integration |
| Provider selection, deterministic fallback, provider failure | answer composer/planner | `test_answer_composer.py`, graph streaming failure tests, ChatService tests, no-provider evaluation case | Covered without network | Live OpenAI response quality and quota/retry behavior |
| Orchestration response shape and trace safety | `orchestrator/*` | graph/service tests, deterministic evaluator shape/safety dimensions | Covered | Property-based fuzzing of arbitrary graph state |
| JSON HTTP endpoint contracts | `dev_server.py` | auth tests and `test_local_http_surface.py` | Covered | Production ASGI adapter (not implemented) |
| SSE event framing/ordering/disconnects (present in base) | `app/api/streaming.py`, dev server | `tests/unit/api/test_streaming.py`, existing ChatService/graph streaming tests | Covered | Browser `EventSource` interoperability and backpressure at scale |
| Static frontend auth/event/security contracts | `frontend/static/*` | `test_static_chat_ui.py`, `test_frontend_security_contract.py` | Covered statically | Browser automation, visual regression, real DOM event execution |
| Offline model-quality evaluation dataset | `tests/evaluation/dataset.json` | 14 stable cases; `scripts/run_evaluation.py` | Covered | Human review and live provider scoring |

## Evaluation case categories

The v1 dataset includes public knowledge, manager/IT role-scoped retrieval,
CEO executive access, employee executive denial, public SQL validation-only,
finance SQL denial, ticket creation, ticket clarification/malformed intent,
casual, prompt injection, empty input, and no-provider general knowledge. Each
case declares user, profile, role, expected category/route/status/access,
required facts, citation expectations, forbidden leakage/claims, and all six
evaluator dimensions.

## Local HTTP smoke

`tests/unit/api/test_local_http_surface.py` starts the repository's supported
stdlib server on an ephemeral loopback port and uses `http.client`. It covers
login/session ownership, public cited chat, denied chat, malformed/empty chat,
ticket action, no-provider fallback, invalid feedback and safe retry, invalid
cookie, unknown route, and feedback identity tampering. It is intentionally
named as a unit-discovered integration contract so the ordinary test command
runs it without a browser or external service.

A browser smoke may be run manually when `chrome-devtools-axi` or Playwright is
available, but it is not a default acceptance dependency. There is no committed
browser harness in this base; adding one is a separate follow-up for the
remaining visual and DOM execution rows.
