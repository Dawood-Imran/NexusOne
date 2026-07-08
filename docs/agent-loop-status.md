# Agent Loop Status

## Current Summary

- State: in-progress
- Active phase: Phase 3 - Main LangGraph Orchestrator
- Last run: full unit suite and compile checks passed on 2026-07-08
- Main risks:
  - FastAPI/React production adapters are not wired yet; the app still uses a framework-independent service layer plus stdlib dev server.
  - Final answer composition is now a required graph node. It uses LangChain OpenAI when `OPENAI_API_KEY` is configured and falls back to deterministic composition on local/model errors.
  - `PROJECT_CONTEXT.md` previously claimed SQL modules existed while the working tree had them deleted; Phase 0 restored the modules and recorded this drift.
  - Local server restart for final Playwright pass was blocked by sandbox approval timeouts after an initial successful page load.
  - LangSmith hosted upload can fail noisily in restricted-network shells when tracing is enabled in the environment; graph execution still succeeds and safe metadata config is covered by unit tests.

## Requirement Coverage

| Requirement | Owner | Status | Evidence | Notes |
|---|---|---|---|---|
| Fake role/profile switching | Frontend/Backend | partial | `app/auth/profiles.py`, `frontend/static/index.html` | Demo profiles are exposed through `/api/profiles`. |
| Role-aware chat UI | Frontend | partial | `frontend/static/index.html`, `frontend/static/app.js`, initial Playwright snapshot | Static shell first, React later if dependencies are added. |
| Permission-aware document Q&A | Backend | partial | `app/retrieval/chunk_index.py`, `app/retrieval/local_kb.py`, `app/ingestion/build_index.py`, ingestion/retrieval/service tests pass | FAISS hybrid retrieval is wired into the main graph with metadata lexical fallback. |
| Citations | Backend/Frontend | partial | `app/agents/orchestrator/nodes.py`, `app/agents/orchestrator/answer_composer.py`, `frontend/static/app.js` source renderer, `tests/unit/frontend/test_static_chat_ui.py` | Answers include inline `[n]` source markers; citation payloads include permitted chunk text for frontend source cards. Combined answers now render document citations and SQL source metadata together. PDF page citations are metadata-level for now. |
| Structured SQL connector | Backend | partial | `app/agents/sql_subgraph`, `app/agents/orchestrator` | Main graph routes structured questions to the independent SQL subgraph; live execution depends on configured Postgres executor. |
| Ticket status lookup | Backend | partial | SQL subgraph validates scoped ticket queries; main graph can route ticket questions | Ticket creation remains Phase 4. |
| Ticket creation | Backend | not-started | Phase 4 | Needs persistence flow and clarification state. |
| Restricted-data refusal | Backend/Frontend | partial | SQL validator, presenter, guardrail service tests pass | Browser denial interaction still needs final Playwright pass. |
| Prompt-injection resistance | Backend | partial | `tests/unit/services/test_guardrail_policy.py`, `tests/unit/services/test_chat_service.py`, `tests/unit/agents/orchestrator/test_graph.py` | Main graph denies before retrieval, SQL, or model/tool work. |
| Feedback capture | Backend/Frontend | not-started | Phase 4 | Schema exists; API not exposed yet. |
| Audit metadata | Backend | not-started | Phase 4 | Schema exists; service writes not implemented. |
| Evaluation tests | Testing | partial | Existing SQL unit tests | Broader role/RAG/E2E tests pending. |
| Responsive frontend | Frontend/Testing | not-started | Phase 1 | Playwright MCP review planned after shell exists. |
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
| `./venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | 61 tests after combined SQL+RAG/source rendering regressions were added. |
| `./venv/bin/python -m compileall app scripts` | pass | Python syntax/import compile check for app and scripts after Phase 3. |
| `./venv/bin/python -m unittest tests.unit.agents.orchestrator.test_graph tests.unit.frontend.test_static_chat_ui tests.unit.services.test_chat_service` | pass | 14 focused tests for graph routing, combined citations/sources, frontend source rendering contract, and chat service behavior. |
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
| OI-004 | Frontend | medium | No frontend existed before this loop. | Build static app shell in Phase 1. |
| OI-005 | Testing | medium | No committed Playwright E2E coverage exists. | Add after local app shell stabilizes. |
| OI-006 | Testing | low | Final Playwright restart was not completed due sandbox approval timeout. | User can run `./venv/bin/python scripts/run_web_app.py --port 8010`; rerun Playwright once server is available. |
| OI-007 | Observability | low | LangSmith upload attempts fail in restricted-network shells if hosted tracing is enabled through environment variables. | Keep tracing config safe; verify hosted traces only when network and credentials are intentionally available. |

## Phase Progress

| Phase | Status | Done | Issues/Notes |
|---|---|---|---|
| Phase 0 | complete | Source docs created; SQL subgraph restored; existing unit tests pass. | Working tree had deleted tracked modules; restored with stricter current tests. |
| Phase 1 | partial | Profile service, guardrail policy, local KB retriever, chat service facade, stdlib HTTP API, static frontend shell, and service tests. | Final browser interaction test remains. |
| Phase 2 | complete | Markdown/PDF-source loader, deterministic chunker, chunk metadata writer, FAISS writer, ingestion report, FAISS hybrid retriever, lexical fallback, retrieval tests. | Metadata exists at `data/faiss/nexusone_chunks_metadata.jsonl`; FAISS index exists at `data/faiss/nexusone_chunks.index`. |
| Phase 3 | in-progress | Main LangGraph orchestrator added with load user, guardrail precheck, deterministic router, SQL subgraph route, RAG route, combined route, validation node, required final answer composition node, inline citation markers, source chunk payloads, combined citation+SQL source UI rendering, LangSmith-compatible run config, final response node, CLI runner, diagram, and tests. | Browser-level Playwright E2E coverage remains. |
| Phase 4 | pending | None | Requires ticket creation and feedback APIs. |
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
