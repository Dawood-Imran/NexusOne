# Agent Loop Status

## Current Summary

- State: in-progress
- Active phase: Phase 4 - Ticket Actions and Feedback
- Last run: full unit suite, frontend contract checks, and Playwright MCP UI inspection passed on 2026-07-08
- Main risks:
  - FastAPI/React production adapters are not wired yet; the app still uses a framework-independent service layer plus stdlib dev server.
  - Final answer composition is now a required graph node. It uses LangChain OpenAI when `OPENAI_API_KEY` is configured and falls back to deterministic composition on local/model errors.
  - `PROJECT_CONTEXT.md` previously claimed SQL modules existed while the working tree had them deleted; Phase 0 restored the modules and recorded this drift.
  - Playwright MCP is now available in this session and was used for manual desktop/mobile UI inspection. Committed Playwright E2E coverage is still pending.
  - LangSmith hosted upload can fail noisily in restricted-network shells when tracing is enabled in the environment; graph execution still succeeds and safe metadata config is covered by unit tests.

## Requirement Coverage

| Requirement | Owner | Status | Evidence | Notes |
|---|---|---|---|---|
| Fake role/profile switching | Frontend/Backend | partial | `app/auth/profiles.py`, `frontend/static/index.html` | Demo profiles are exposed through `/api/profiles`. |
| Role-aware chat UI | Frontend | partial | `frontend/static/index.html`, `frontend/static/app.js`, `frontend/static/styles.css`, `tests/unit/frontend/test_static_chat_ui.py` | Static UI now has demo authentication, profile-scoped conversation history, chat workspace, and right inspector. Browser E2E remains. |
| Permission-aware document Q&A | Backend | partial | `app/retrieval/chunk_index.py`, `app/retrieval/local_kb.py`, `app/ingestion/build_index.py`, ingestion/retrieval/service tests pass | FAISS hybrid retrieval is wired into the main graph with metadata lexical fallback. |
| Citations | Backend/Frontend | partial | `app/agents/orchestrator/nodes.py`, `app/agents/orchestrator/answer_composer.py`, `frontend/static/app.js` inspector source renderer, `tests/unit/frontend/test_static_chat_ui.py` | Answers include inline `[n]` source markers; citation payloads include permitted chunk text in the right inspector. Combined answers preserve document citations and SQL source metadata. PDF page citations are metadata-level for now. |
| Structured SQL connector | Backend | partial | `app/agents/sql_subgraph`, `app/agents/orchestrator` | Main graph routes structured questions to the independent SQL subgraph; live execution depends on configured Postgres executor. |
| Ticket status lookup | Backend | partial | SQL subgraph validates scoped ticket queries; main graph can route ticket questions | Status lookup remains read-only through the SQL subgraph. |
| Ticket creation | Backend/Frontend | partial | `app/actions/ticket_service.py`, `app/agents/orchestrator/action_routing.py`, `app/agents/orchestrator/nodes.py`, `frontend/static/app.js`, `tests/unit/actions/test_ticket_service.py`, `tests/unit/agents/orchestrator/test_graph.py`, `scripts/smoke_phase4_actions.py` | IT/HR/Admin creation route is wired with clarification and safe ticket payloads. Live Postgres write smoke passed. Browser E2E remains. |
| Restricted-data refusal | Backend/Frontend | partial | SQL validator, presenter, guardrail service tests pass | Browser denial interaction still needs final Playwright pass. |
| Prompt-injection resistance | Backend | partial | `tests/unit/services/test_guardrail_policy.py`, `tests/unit/services/test_chat_service.py`, `tests/unit/agents/orchestrator/test_graph.py` | Main graph denies before retrieval, SQL, or model/tool work. |
| Feedback capture | Backend/Frontend | partial | `app/actions/feedback_service.py`, `app/api/dev_server.py`, `frontend/static/app.js`, `tests/unit/actions/test_feedback_service.py`, `scripts/smoke_phase4_actions.py` | `/api/feedback` stores validated feedback through service layer; live Postgres and HTTP API smokes passed. Browser E2E remains. |
| Audit metadata | Backend | partial | `app/actions/audit_service.py`, `app/services/chat_service.py`, `tests/unit/actions/test_audit_service.py`, `tests/unit/services/test_chat_service.py`, `scripts/smoke_phase4_actions.py` | Chat service writes safe metadata with redacted query text; live Postgres smoke passed. |
| Evaluation tests | Testing | partial | Existing SQL unit tests | Broader role/RAG/E2E tests pending. |
| Responsive frontend | Frontend/Testing | partial | `frontend/static/styles.css`, static frontend contract tests, Playwright MCP snapshots | UI Pro Max pass compacted auth, improved touch targets/focus states, removed feedback from non-answer welcome state, and verified desktop/mobile drawer behavior. Committed browser E2E remains. |
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
| `python3 .agents/skills/ui-ux-pro-max/scripts/search.py "internal enterprise AI knowledge assistant support desk dashboard professional" --design-system --variance 4 --motion 3 --density 8 -p "NexusOne Copilot"` | pass | Used UI Pro Max guidance for dense professional dashboard spacing, accessibility, touch targets, reduced motion, and interaction states. Palette recommendation was not copied because it was too AI-purple for this enterprise tool. |
| `node --check frontend/static/app.js` | pass | JavaScript syntax check after frontend state rewrite. |
| `./venv/bin/python -m unittest tests.unit.frontend.test_static_chat_ui` | pass | 9 static frontend contract tests after UI Pro Max pass, mobile inspector ARIA state, and welcome-message feedback suppression. |
| `./venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 79 tests after UI Pro Max frontend refinement. |
| Playwright MCP desktop auth/workspace inspection on `http://127.0.0.1:8014` | pass | Verified compact auth layout, scrollable profile list, 44px controls, and welcome state without answer feedback. |
| Playwright MCP mobile workspace inspection at `390x844` | pass | Verified stacked conversation layout, accessible details drawer, mobile touch targets, and drawer close behavior. |
| Local static asset smoke on `http://127.0.0.1:8012` | pass | HTML/CSS/JS served with auth view, app view, conversation list, inspector, and profile-scoped conversation markers. |
| `./venv/bin/python -m compileall app scripts` | pass | Python syntax/import compile check for app and scripts after Phase 4 action wiring. |
| `./venv/bin/python -m unittest tests.unit.agents.orchestrator.test_graph tests.unit.frontend.test_static_chat_ui tests.unit.services.test_chat_service` | pass | 14 focused tests for graph routing, combined citations/sources, frontend source rendering contract, and chat service behavior. |
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

## Open Issues

| ID | Owner | Severity | Description | Next Action |
|---|---|---|---|---|
| OI-001 | Backend | medium | FastAPI dependency may now be installed locally, but production API adapter is not implemented yet. | Add FastAPI adapter in Phase 5 unless needed earlier. |
| OI-002 | Backend | closed | FAISS binary index exists and retriever uses `faiss_hybrid` when metadata/index align. | Keep lexical fallback for stale or missing FAISS files. |
| OI-003 | Backend | medium | SQL live execution requires local Postgres and safe helper functions. | Keep SQL subgraph executable independently; add integration test once DB is available. |
| OI-004 | Frontend | closed | Static frontend now has an auth-first conversation workspace instead of a demo role-selector shell. | Continue visual refinement through browser E2E/review. |
| OI-005 | Testing | medium | No committed Playwright E2E coverage exists. | Add after local app shell stabilizes. |
| OI-006 | Testing | medium | Browser-level committed Playwright E2E is not completed. Manual Playwright MCP inspection is available and passed for auth/workspace/mobile drawer. | Add a committed E2E harness for ticket creation, cited answer inspection, feedback, and restricted-denial journeys. |
| OI-007 | Observability | low | LangSmith upload attempts fail in restricted-network shells if hosted tracing is enabled through environment variables. | Keep tracing config safe; verify hosted traces only when network and credentials are intentionally available. |

## Phase Progress

| Phase | Status | Done | Issues/Notes |
|---|---|---|---|
| Phase 0 | complete | Source docs created; SQL subgraph restored; existing unit tests pass. | Working tree had deleted tracked modules; restored with stricter current tests. |
| Phase 1 | partial | Profile service, guardrail policy, local KB retriever, chat service facade, stdlib HTTP API, static frontend shell, and service tests. | Final browser interaction test remains. |
| Phase 2 | complete | Markdown/PDF-source loader, deterministic chunker, chunk metadata writer, FAISS writer, ingestion report, FAISS hybrid retriever, lexical fallback, retrieval tests. | Metadata exists at `data/faiss/nexusone_chunks_metadata.jsonl`; FAISS index exists at `data/faiss/nexusone_chunks.index`. |
| Phase 3 | in-progress | Main LangGraph orchestrator added with load user, guardrail precheck, deterministic router, SQL subgraph route, RAG route, combined route, validation node, required final answer composition node, inline citation markers, source chunk payloads, combined citation+SQL source UI rendering, LangSmith-compatible run config, final response node, CLI runner, diagram, and tests. | Browser-level Playwright E2E coverage remains. |
| Phase 4 | in-progress | Deterministic ticket action services, in-memory and SQLAlchemy repositories, ticket creation graph route, clarification responses, `/api/feedback`, auth-first frontend, profile-scoped conversation history, inspector-based sources/tickets/trace, feedback controls, UI Pro Max refinement, Playwright MCP desktop/mobile inspection, safe audit metadata service, live Postgres smoke, and HTTP API/static asset smoke. | Committed browser E2E remains. |
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
