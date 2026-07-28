# Agent Loop Status

## Current Summary

- State: integration-ready
- Active phase: Phase 4 - Ticket Actions and Feedback / integration branch validation complete
- Last run: the three captain-approved branches were merged from clean `daud_dev`; 155 focused contracts, the 230-test deterministic suite, the 20-case offline evaluator, Python compilation, JavaScript syntax, diff checks, and actual local HTTP/SSE smoke passed. OpenAI/Postgres live paths were intentionally not exercised.
- Integration note: `docs/requirements-coverage.md` is retained as the frontend/audit branch's durable R1-R14 evidence matrix; the integrated UI preserves the action-aware conversation inspector and adds loading, denied, no-answer, error/retry, responsive, auto-growing composer, and authenticated account-session states. The frontend no longer exposes a demo profile picker or post-login role switcher; it consumes `/api/auth/session`, `/api/auth/login`, and `/api/auth/logout`. The current UI polish keeps ticket cards structured-only, adds independent keyboard-accessible left/right panel toggles, stores a per-answer expandable trace, collapses prior traces on new questions, and removes provider/fallback diagnostics and obsolete shell copy.
- Main risks:
  - FastAPI/React production adapters are not wired yet; the app still uses a framework-independent service layer plus stdlib dev server.
  - The stdlib web entry point now loads the repository `.env` before constructing ChatService; safe capability metadata reports live SQL versus local validation-only mode and provider fallback reasons without values.
  - Final answer composition is now a required graph node. It uses LangChain OpenAI when `OPENAI_API_KEY` is configured and falls back to deterministic composition on local/model errors.
  - `PROJECT_CONTEXT.md` previously claimed SQL modules existed while the working tree had them deleted; Phase 0 restored the modules and recorded this drift.
  - Playwright MCP is now available in this session and was used for manual desktop/mobile UI inspection. Committed Playwright E2E coverage is still pending.
  - LangSmith hosted upload can fail noisily in restricted-network shells when tracing is enabled in the environment; graph execution still succeeds and safe metadata config is covered by unit tests.
- The local authentication contract now uses salted password verifiers, opaque server-side sessions, and cookie-authenticated chat/feedback; the static UI uses that contract and omits client identity from chat/feedback requests.
- Server memory phase: `docs/conversation-memory.md` records the pre-change inventory and official LangChain references. `SQLiteConversationStore` now owns server conversation IDs/turns, and JSON user memory/tools own bounded per-user durable facts/preferences; frontend history now reloads from authenticated conversation endpoints instead of browser persistence.
- Integration branch: merged `ecc62fc`, `583abad`, and `4a30982` from clean `daud_dev` with memory, retrieval threshold/citation, ticket ownership/security, frontend, routing, and streaming contracts retained; `docs/intent-routing.md` and the offline history fixture were aligned to the server-memory contract.

## Memory Coverage

| Layer | Evidence | Status |
|---|---|---|
| Short-term owner-scoped threads | `app/memory/conversation_store.py`, `app/services/chat_service.py`, authenticated `/api/conversations`, `tests/unit/memory/test_conversation_store.py`, `tests/unit/services/test_memory_integration.py`, `tests/unit/api/test_conversation_memory_http.py` | complete locally |
| Long-term per-user profiles/tools | `app/memory/user_memory.py`, `app/memory/tools.py`, `app/memory/extraction.py`, `tests/unit/memory/test_user_memory.py`, memory integration tests | complete locally |
| LangGraph thread/config bridge | `app/observability/langsmith.py`, `app/agents/orchestrator/graph.py`, `docs/conversation-memory.md` | repository-owned checkpointer equivalent; replaceable for production |
| Frontend/API lifecycle | `frontend/static/app.js`, `app/api/dev_server.py`, `docs/authentication.md` | complete locally |

## Requirement Coverage

| Requirement | Owner | Status | Evidence | Notes |
|---|---|---|---|---|
| Local username/password authentication | Backend | complete | `app/auth/service.py`, `app/api/dev_server.py`, `docs/authentication.md`, `tests/unit/auth/test_auth_service.py`, `tests/unit/api/test_dev_server_auth.py` | Synthetic accounts use salted password verifiers and opaque HttpOnly sessions; no external IdP is involved. |
| Authenticated identity and role-aware chat UI | Frontend/Backend | partial | `app/api/dev_server.py`, `frontend/static/index.html`, `frontend/static/app.js`, `frontend/static/styles.css`, `tests/unit/frontend/test_static_chat_ui.py` | Backend derives identity from the session; the static UI uses username/password auth, an immutable server-returned account/popover, profile-scoped conversation history, and a conversation/source/trace inspector. Browser E2E remains.
| Permission-aware document Q&A | Backend | partial | `app/retrieval/chunk_index.py`, `app/retrieval/config.py`, `app/retrieval/embeddings.py`, `app/retrieval/access.py`, `app/ingestion/build_index.py`, `docs/retrieval.md`, and hybrid retrieval tests pass | Local LSA hybrid retrieval normalizes public scores to 0-100, applies the inclusive 50 relevance policy after authorization, de-duplicates documents, and returns a no-reference outcome without below-threshold context; metadata lexical fallback uses the same policy. |
| Citations | Backend/Frontend | partial | `app/agents/orchestrator/nodes.py`, `app/agents/orchestrator/answer_composer.py`, `frontend/static/app.js` inspector source renderer, `tests/unit/agents/orchestrator/test_answer_composer.py`, and retrieval/graph tests | Inline markers are assigned only to retained, ranked, authorized sources; citations include title/path/0-100 score metadata, invalid provider markers are removed, and no-reference turns emit no citation. Combined answers preserve document citations and SQL source metadata. PDF page citations are metadata-level for now. |
| Structured SQL connector | Backend | partial | `app/agents/sql_subgraph`, `app/agents/orchestrator`, `app/services/chat_service.py`, runtime/service tests | Main graph routes structured questions to the independent SQL subgraph; HTTP ChatService injects the configured `DATABASE_URL` executor, returns sanitized rows, and labels disconnected requests validation-only. |
| Ticket status lookup | Backend | partial | SQL subgraph validates scoped ticket queries; main graph can route ticket questions | Status lookup remains read-only through the SQL subgraph. |
| Ticket creation | Backend/Frontend | partial | `app/actions/ticket_service.py`, `app/agents/orchestrator/action_routing.py`, `app/agents/orchestrator/nodes.py`, `frontend/static/app.js`, `tests/unit/actions/test_ticket_service.py`, `tests/unit/agents/orchestrator/test_graph.py`, `scripts/smoke_phase4_actions.py` | IT/HR/Admin creation route is wired with clarification and safe ticket payloads. Live Postgres write smoke passed. Browser E2E remains. |
| Restricted-data refusal | Backend/Frontend | partial | SQL validator, presenter, guardrail service tests pass | Browser denial interaction still needs final Playwright pass. |
| Prompt-injection resistance | Backend | partial | `tests/unit/services/test_guardrail_policy.py`, `tests/unit/services/test_chat_service.py`, `tests/unit/agents/orchestrator/test_graph.py` | Main graph denies before retrieval, SQL, or model/tool work. |
| Feedback capture | Backend/Frontend | partial | `app/actions/feedback_service.py`, `app/api/dev_server.py`, `frontend/static/app.js`, `tests/unit/actions/test_feedback_service.py`, `scripts/smoke_phase4_actions.py` | `/api/feedback` stores validated feedback through service layer; live Postgres and HTTP API smokes passed. Browser E2E remains. |
| Audit metadata | Backend | partial | `app/actions/audit_service.py`, `app/services/chat_service.py`, `tests/unit/actions/test_audit_service.py`, `tests/unit/services/test_chat_service.py`, `scripts/smoke_phase4_actions.py` | Chat service writes safe metadata with redacted query text; live Postgres smoke passed. |
| Evaluation tests | Testing | partial | Existing SQL unit tests | Broader role/RAG/E2E tests pending. |
| Responsive frontend | Frontend/Testing | partial | `frontend/static/styles.css`, static frontend contract tests, `docs/requirements-coverage.md` | Integrated action-aware conversation workspace retains authenticated session handling, immutable account control, profile-scoped history, inspector, tickets, and feedback while adding loading/denied/no-answer/error-retry states, source metadata, focus/touch treatment, auto-growing composer behavior, and reduced-motion support. Browser E2E remains. |
| Observability hooks | Backend | partial | `app/observability/langsmith.py`, `app/agents/orchestrator/graph.py`, graph trace response fields | Graph invocations now include LangSmith-compatible run name, tags, and safe metadata. Hosted LangSmith verification depends on env credentials. |

## Guardrail Coverage

| Policy | Roles Allowed | Roles Denied | Test Evidence | Status |
|---|---|---|---|---|
| Public internal docs | all active roles | inactive/unknown users | Local KB/service tests pass | partial |
| Finance budgets | finance, executive, ceo | employee, manager, hr, it_admin, admin_ops | SQL scope tests pass | partial |
| Revenue risks | executive, ceo | employee, manager, hr, finance, it_admin, admin_ops | SQL scope tests pass | partial |
| Ticket raw IDs hidden | none in final output | all roles | presentation tests pass | partial |
| Safe assignment names | accessible ticket viewers only | inaccessible ticket viewers | presentation and graph tests pass | partial |
| Prompt injection | none | all unsafe requests | Guardrail/service tests pass | partial |

## Test Runs

| Command | Result | Notes |
|---|---|---|
| `./venv/bin/python scripts/build_rag_index.py` | pass | Wrote 106 chunks from 71 documents; `faiss_status=written`. |
| `./venv/bin/python -m unittest tests.unit.agents.orchestrator.test_graph` | pass | 4 Phase 3 routing tests: RAG, SQL, denied, combined. |
| `./venv/bin/python -m unittest tests.unit.retrieval.test_chunk_index tests.unit.agents.orchestrator.test_graph tests.unit.services.test_chat_service` | pass | 12 focused regression tests after FAISS hybrid retrieval and graph service handoff. |
| `./venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 77 tests after auth/conversation frontend redesign contract coverage was added. |
| `python3 -m unittest tests.unit.auth.test_auth_service tests.unit.api.test_dev_server_auth` | pass | Focused local password verifier, login/session/logout, safe profile, unauthenticated endpoint, identity tampering, and immutable role contract tests. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 83 tests after integrating the frontend/audit branch and resolving the frontend contract merge. |
| `.venv/bin/python -m unittest tests.unit.auth.test_auth_service tests.unit.api.test_dev_server_auth` | pass | 13 focused authentication/API contract tests after installing `requirements.txt` into the isolated `.venv`. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 96 tests after installing the project requirements into the isolated `.venv`; no test failures. |
| `.venv/bin/python -m compileall -q app scripts tests` + `node --check frontend/static/app.js` | pass | Python and existing static JavaScript syntax validation. |
| `.venv/bin/python scripts/run_web_app.py` + local HTTP auth/chat smoke | pass | Verified unauthenticated denial, login cookie/current-session persistence, server-owned chat profile, identity tampering rejection, and logout. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 92 tests after runtime `.env` loading, HTTP executor injection, live/local capability contracts, provider selection, safe SQL rows, and trace metadata coverage. |
| `node --check frontend/static/app.js` | pass | Structured-row inspector and graph/SQL subgraph trace rendering syntax check. |
| `git diff --check` | pass | No whitespace errors in the runtime connectivity change. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 105 integrated tests after resolving authentication/runtime/frontend conflicts. |
| `.venv/bin/python -m compileall -q app scripts tests` + `node --check frontend/static/app.js` | pass | Final Python and JavaScript syntax checks. |
| Local HTTP contract smoke on `http://127.0.0.1:8017` | pass | Auth/session/logout, authenticated chat identity, tampering rejection, restricted denial, citations, SQL response shape, graph/subgraph trace, feedback, deterministic answer, and validation-only SQL; no repository `.env`, OpenAI, or Postgres live path. |
| chrome-devtools-axi smoke on `http://127.0.0.1:8020` and `http://127.0.0.1:8021` | pass | Sign-in, authenticated workspace, immutable account popover, sidebar, cited answer/source inspector, capability status, 20-line auto-growing composer, and 390x844 responsive layout. |
| `.venv/bin/python -m unittest tests.unit.actions.test_ticket_service tests.unit.actions.test_feedback_service tests.unit.actions.test_audit_service tests.unit.agents.orchestrator.test_graph tests.unit.services.test_chat_service tests.unit.frontend.test_static_chat_ui` | pass | 36 focused action, graph/service, and frontend contract tests. |
| `./.venv/bin/python -m unittest tests.unit.frontend.test_static_chat_ui` | pass | 19 focused frontend contracts for structured ticket/error cards, independent panel toggles, per-answer trace collapse/reopen behavior, copy removal, and auth/session UI. |
| `./.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 109-test full suite after the authenticated-chat UI corrections. |
| `./.venv/bin/python -m compileall -q app scripts tests` + `node --check frontend/static/app.js` + `git diff --check` | pass | Python/JavaScript syntax and whitespace validation after panel, trace, and ticket rendering changes. |
| `.venv/bin/python scripts/run_orchestrator.py --deterministic-composer --user-id u001 --trace "Create an IT ticket for AWS sandbox access needed for billing migration."` | pass | Ticket action returned `ticket_created`; trace showed guardrail precheck and `run_ticket_action` without RAG/SQL nodes. |
| `.venv/bin/python scripts/run_web_app.py` + local HTTP assertions | pass | Static HTML/CSS/JS markers, 8 profiles, allowed/denied chat, and feedback API response verified. Browser automation was not run. |
| `python3 .agents/skills/ui-ux-pro-max/scripts/search.py "internal enterprise AI knowledge assistant support desk dashboard professional" --design-system --variance 4 --motion 3 --density 8 -p "NexusOne Copilot"` | pass | Used UI Pro Max guidance for dense professional dashboard spacing, accessibility, touch targets, reduced motion, and interaction states. Palette recommendation was not copied because it was too AI-purple for this enterprise tool. |
| `node --check frontend/static/app.js` | pass | JavaScript syntax check after frontend auth/account/composer rewrite. |
| `python3 -m unittest tests.unit.frontend.test_static_chat_ui` | pass | 9 focused static/interaction contracts for username/password login, immutable account identity, account popover, conversation rail, composer auto-resize, suggestions, states, and responsive behavior. |
| `CHROME_DEVTOOLS_AXI_SESSION=nexusone-ui-7p6 chrome-devtools-axi` static auth/workspace inspection | pass | Verified sign-in loading/backend-unavailable state at desktop and mobile sizes, injected authenticated workspace rendering, account popover details, suggestion fill/focus, and multiline composer auto-resize with usable send action. |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | environment-limited | Frontend and 63 other tests collected; 3 backend-dependent modules could not import because system Python lacks `langgraph`. |
| `./venv/bin/python -m unittest tests.unit.frontend.test_static_chat_ui` | pass | 9 static frontend contract tests after UI Pro Max pass, mobile inspector ARIA state, and welcome-message feedback suppression. |
| `./venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 79 tests before this integration; final integrated run is recorded above with 83 tests. |
| Playwright MCP desktop auth/workspace inspection on `http://127.0.0.1:8014` | pass | Verified compact auth layout, scrollable profile list, 44px controls, and welcome state without answer feedback. |
| Playwright MCP mobile workspace inspection at `390x844` | pass | Verified stacked conversation layout, accessible details drawer, mobile touch targets, and drawer close behavior. |
| Local static asset smoke on `http://127.0.0.1:8012` | pass | HTML/CSS/JS served with auth view, app view, conversation list, inspector, and profile-scoped conversation markers. |
| `./venv/bin/python -m compileall app scripts` | pass | Python syntax/import compile check for app and scripts after Phase 4 action wiring. |
| `./venv/bin/python -m unittest tests.unit.agents.orchestrator.test_graph tests.unit.frontend.test_static_chat_ui tests.unit.services.test_chat_service` | pass | 14 focused tests for graph routing, combined citations/sources, frontend source rendering contract, and chat service behavior. |
| `OPENAI_API_KEY='' DATABASE_URL='' .venv/bin/python -m unittest tests.unit.memory.test_conversation_store tests.unit.memory.test_user_memory tests.unit.services.test_memory_integration tests.unit.api.test_conversation_memory_http tests.unit.api.test_streaming` | pass | 23 focused memory, ownership/isolation, retention, replay/concurrency, profile validation/locking, server-controlled tools, HTTP lifecycle, and SSE identifier tests. |
| `OPENAI_API_KEY='' DATABASE_URL='' LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 208 deterministic tests after server memory integration. |
| Local in-process HTTP/SSE smoke with `ThreadingHTTPServer`, injected fake classifier/composer, and temporary runtime directory | pass | Authenticated UUID conversation creation, same-thread history recall, separate-thread isolation, explicit profile-memory update/read, and SSE start/complete IDs verified without OpenAI/Postgres/network. |
| `.venv/bin/python -m compileall -q app tests scripts` + `node --check frontend/static/app.js` + `git diff --check` | pass | Final Python compilation, JavaScript syntax, and whitespace validation after server memory changes. |
| `./venv/bin/python -m unittest tests.unit.actions.test_ticket_service tests.unit.actions.test_feedback_service tests.unit.actions.test_audit_service tests.unit.agents.orchestrator.test_graph tests.unit.services.test_chat_service tests.unit.frontend.test_static_chat_ui` | pass | 28 focused Phase 4 tests for deterministic ticket actions, feedback, audit metadata, graph routing, and frontend contracts. |
| `./venv/bin/python scripts/run_orchestrator.py --deterministic-composer --user-id u001 --trace "Create an IT ticket for AWS sandbox access needed for billing migration."` | pass | Ticket action route returned `ticket_created`, safe ticket payload, and trace without RAG/SQL nodes. LangSmith hosted upload still failed due restricted network. |
| `./venv/bin/python scripts/smoke_phase4_actions.py` | pass | Live Postgres smoke passed outside sandbox. Created ticket `IT-1047`, feedback `1`, and audit `1`; verified `tickets`, `ticket_events`, `feedback`, and `audit_logs`. |
| Local `/api/chat` ticket creation smoke on `http://127.0.0.1:8011` | pass | Returned `ticket_created` for ticket `IT-1048`; trace showed `run_ticket_action` and no RAG/SQL nodes. |
| Local `/api/feedback` smoke on `http://127.0.0.1:8011` | pass | Returned `stored` with feedback id `2`. |
| Local `/api/chat` clarification smoke on `http://127.0.0.1:8011` | pass | Returned `needs_clarification` with missing fields `department`, `category`, and `description`. |
| Local `/api/chat` smoke test on `http://127.0.0.1:8010` | pass | AWS answer included `[1]`; citation `[1]` included the AWS chunk text containing the ticket request step. |
| `./venv/bin/python scripts/run_orchestrator.py --user-id u001 --execute-sql "What holidays apply in Pakistan?"` | pass | Live Postgres smoke test passed outside sandbox; returned 3 Pakistan holiday rows. |
| `./venv/bin/python scripts/run_orchestrator.py --user-id u001 --trace "How do I request AWS access?"` | pass | OpenAI final composer passed outside sandbox; trace showed `compose_final_answer` with `backend=openai:gpt-4.1-mini` and preserved AWS request steps. |
| Playwright MCP initial page load at `http://127.0.0.1:8010` | partial | Page rendered and snapshot captured; console only showed missing favicon before fix. Final restart was blocked by sandbox approval timeout. |
| `python3 -m unittest tests.unit.retrieval.test_config tests.unit.retrieval.test_hybrid_retrieval tests.unit.retrieval.test_permission_boundaries tests.unit.services.test_local_kb` | pass | 23 deterministic offline retrieval tests covering lexical exact matches, semantic paraphrases, mixed ranking, 49.99/50/50.01 boundaries, duplicate documents, authorization-before-embedding, prompt-injection excerpts, and fallback access. |
| `.venv/bin/python -m unittest tests.unit.retrieval.test_config tests.unit.retrieval.test_hybrid_retrieval tests.unit.agents.orchestrator.test_answer_composer tests.unit.agents.orchestrator.test_graph tests.unit.services.test_chat_service` | pass | 49 focused tests covering normalized 0-100 scores, no-reference graph behavior, citation marker integrity, source prompt-injection handling, service capabilities, and HTTP-facing response decoration. |
| `.venv/bin/python -m unittest tests.unit.api.test_local_http_surface tests.unit.api.test_streaming` | pass | 13 local HTTP/SSE contract tests passed with injected deterministic classifier/composer; cited AWS response, trace safety, auth, denied paths, and streaming remained green without OpenAI/Postgres/network. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 196-test full offline suite passed. |
| `.venv/bin/python -m compileall -q app scripts tests` + `node --check frontend/static/app.js` + `git diff --check` | pass | Python compilation, JavaScript syntax, and whitespace validation passed after retrieval threshold changes. |
| `git merge --no-ff ecc62fc`, `583abad`, `4a30982` | pass | Three captain-approved commits are ancestors of the integration branch; only the deliberate memory/retrieval prompt and memory/retriever constructor conflicts were resolved. No source branch was changed. |
| `.venv/bin/python -m unittest` focused memory/retrieval/ticket/routing/frontend/API/streaming contracts | pass | 155 focused tests passed with empty provider/database credentials. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 230 deterministic tests passed locally without production credentials or network services. |
| `.venv/bin/python scripts/run_evaluation.py` | pass | All 20 offline evaluation cases and all six dimensions passed after aligning the history case with server memory. |
| Local `ThreadingHTTPServer` JSON and SSE smoke with temporary runtime data | pass | Auth/session, cited RAG, restricted denial without title leakage, SSE event ordering, and delta/completion consistency passed; no OpenAI/Postgres/network. |
| `.venv/bin/python -m compileall -q app tests scripts` + `node --check frontend/static/app.js` + `git diff --check` | pass | Final Python compilation, JavaScript syntax, and whitespace validation passed; generated runtime data was removed and tracked bytecode restored. |
| Combined diff/reference audit | pass | No newly introduced secrets, duplicate files, untracked runtime data, or unauthorized broad changes found; `.env.example` values remain placeholders/synthetic. |

## Open Issues

| ID | Owner | Severity | Description | Next Action |
|---|---|---|---|---|
| OI-001 | Backend | medium | FastAPI dependency may now be installed locally, but production API adapter is not implemented yet. | Add FastAPI adapter in Phase 5 unless needed earlier. |
| OI-002 | Backend | closed | The retriever now uses local LSA semantic vectors plus lexical matching; the old token-hash FAISS artifact was removed and optional FAISS output is LSA-only. | Keep metadata lexical fallback when NumPy/local semantic construction is unavailable. |
| OI-003 | Backend | medium | SQL live execution requires local Postgres and safe helper functions. | Keep SQL subgraph executable independently; add integration test once DB is available. |
| OI-004 | Frontend | closed | Static frontend now has a username/password auth-first conversation workspace instead of a demo role-selector shell. The signed-in account is immutable, details live in the top-left account popover, and the right inspector is reserved for conversation/source/trace details. | Continue visual refinement through browser E2E/review. |
| OI-005 | Testing | medium | No committed Playwright E2E coverage exists. | Add after local app shell stabilizes. |
| OI-006 | Testing | medium | Browser-level committed Playwright E2E is not completed. Manual Playwright MCP inspection is available and passed for auth/workspace/mobile drawer. | Add a committed E2E harness for ticket creation, cited answer inspection, feedback, and restricted-denial journeys. |
| OI-007 | Observability | low | LangSmith upload attempts fail in restricted-network shells if hosted tracing is enabled through environment variables. | Keep tracing config safe; verify hosted traces only when network and credentials are intentionally available. |
| OI-008 | Frontend | closed | The frontend now uses username/password auth, immutable server-returned identity, cookie-authenticated chat/feedback, and omits client identity from request bodies. | Keep browser/E2E coverage as the remaining validation gap. |
| OI-009 | Backend/Frontend | closed | Server conversation create/list/read/delete, owner-scoped append, replay/idempotency, bounded retention, SSE IDs, and per-user durable profile memory are implemented locally. Legacy browser-only keys are ignored and documented for cleanup. | Replace local SQLite/JSON boundaries with production checkpointer/store when deployment requires it. |

## Phase Progress

| Phase | Status | Done | Issues/Notes |
|---|---|---|---|
| Phase 0 | complete | Source docs created; SQL subgraph restored; existing unit tests pass. | Working tree had deleted tracked modules; restored with stricter current tests. |
| Phase 1 | partial | Profile service, guardrail policy, local KB retriever, chat service facade, stdlib HTTP API, static frontend shell, and service tests. | Final browser interaction test remains. |
| Phase 2 | complete | Markdown/PDF-source loader, deterministic chunker, chunk metadata writer, FAISS writer, ingestion report, FAISS hybrid retriever, lexical fallback, retrieval tests. | Metadata exists at `data/faiss/nexusone_chunks_metadata.jsonl`; FAISS index exists at `data/faiss/nexusone_chunks.index`. |
| Phase 3 | in-progress | Main LangGraph orchestrator added with load user, guardrail precheck, deterministic router, SQL subgraph route, RAG route, combined route, validation node, required final answer composition node, inline citation markers, source chunk payloads, combined citation+SQL source UI rendering, LangSmith-compatible run config, final response node, CLI runner, diagram, and tests. | Browser-level Playwright E2E coverage remains. |
| Phase 4 | in-progress | Deterministic ticket actions, feedback/audit services, graph/API routes, salted local username/password auth with cookie sessions, immutable account popover, profile-scoped conversation history, inspector-based sources/rows/tickets/trace, feedback controls, auto-growing composer, UI Pro Max refinement, repository `.env` loading, configured SQL executor injection, sanitized live rows, provider capability metadata, live Postgres smoke, and HTTP API/static asset smoke. | Committed browser E2E and production hardening remain.
| Phase 5 | pending | None | Requires E2E and production hardening. |

## Understanding Checklist

- [x] Problem and root cause
- [x] Relevant code path or business flow
- [x] Solution and design decision
- [x] Edge cases
- [x] Tests or verification
- [x] Broader impact

## Final Acceptance Checklist

- [ ] Requirements implemented
- [ ] Backend RBAC enforced
- [ ] Guardrail tests pass
- [ ] Playwright journeys pass
- [ ] UI/UX review pass
- [ ] Build passes
- [ ] No known critical issues
