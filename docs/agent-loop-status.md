# Agent Loop Status

## Current Summary

- State: complete (frontend refresh and requirements audit; documented product gaps remain)
- Active phase: Phase 3 - Main LangGraph Orchestrator / frontend quality pass
- Last run: all 65 unit tests, JavaScript/Python compile checks, and local API smoke passed on 2026-07-27
- Main risks:
  - The app still uses a framework-independent service layer plus stdlib dev server; FastAPI/React production adapters are not wired.
  - The static frontend was replaced with a responsive, role-aware workspace and explicit empty/loading/success/denied/no-answer/error-retry states. Browser verification is still unavailable in this checkout.
  - Browser verification remains unavailable because Chrome DevTools MCP and a committed Playwright harness are not present; the disposable `.venv` now runs the full test suite.
  - Ticket creation, feedback capture, and audit writes remain Phase 4 gaps; see `docs/requirements-coverage.md`.
  - LangSmith hosted upload can fail in restricted-network shells when tracing is enabled; safe metadata configuration remains covered by unit tests.

The evidence-backed requirement matrix is maintained in `docs/requirements-coverage.md`. It is the durable audit source; this file records the latest loop state and command outcomes.

## Requirement Coverage

The complete R1–R14 matrix, guardrail contract, PRD mapping, setup-plan mapping, phase status, and explicit gaps are in `docs/requirements-coverage.md`.

| Current area | Status | Evidence | Next gap |
|---|---|---|---|
| Profile-aware shell | partial | `frontend/static/index.html`, `frontend/static/app.js`, `app/auth/profiles.py` | Browser journey proving profile switch changes server response. |
| Guarded RAG/SQL behavior | partial | `app/guardrails/`, `app/retrieval/`, `app/agents/`, all 65 unit tests, and local `/api/chat` allowed/denied smoke | Live executor integration and browser payload scan. |
| Frontend quality/states | partial | `frontend/static/styles.css`, static UI contract tests | Browser/accessibility review. |
| Ticket/feedback/audit scope | missing | `docs/phase4-ticket-actions-feedback-plan.md` is plan-only | Implement Phase 4 services and tests. |

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
| `node --check frontend/static/app.js` | pass | Static JavaScript syntax check after the frontend refresh. |
| `python -m unittest tests.unit.frontend.test_static_chat_ui` | pass | 8 focused tests cover citation/source rendering, profile context, loading/error/denied/retry contracts, selected profile payload, responsive CSS, and reduced motion. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | All 65 unit tests pass in the disposable environment created from `requirements.txt`. |
| `python -m compileall app scripts` | pass | Python syntax/compile check. |
| `git diff --check` | pass | No whitespace errors in the implementation diff. |
| Static HTTP asset smoke (`python -m http.server` + `curl`) | pass | HTML, CSS, and JavaScript assets served successfully; API behavior was not exercised. |
| Local `/api/profiles` + `/api/chat` smoke | pass | 8 profiles loaded; employee AWS question returned citations; employee revenue-risk request was denied without the restricted title; CEO revenue-risk request was accepted by the SQL route (`validated` without Postgres rows). |
| Browser/Playwright smoke | unverifiable | Chrome DevTools MCP is unavailable and no Playwright config is committed. |
| `.venv/bin/python -m pip install -r requirements.txt` | pass | Disposable in-worktree environment installed the declared runtime dependencies; ignored by git. |

## Open Issues

| ID | Owner | Severity | Description | Next Action |
|---|---|---|---|---|
| OI-001 | Backend | medium | FastAPI dependency may now be installed locally, but production API adapter is not implemented yet. | Add FastAPI adapter in Phase 5 unless needed earlier. |
| OI-002 | Backend | closed | FAISS binary index exists and retriever uses `faiss_hybrid` when metadata/index align. | Keep lexical fallback for stale or missing FAISS files. |
| OI-003 | Backend | medium | SQL live execution requires local Postgres and safe helper functions. | Keep SQL subgraph executable independently; add integration test once DB is available. |
| OI-004 | Frontend | closed | The dummy shell was replaced with a deliberate responsive workspace, profile context, source cards, and complete client states. | Keep browser review in the Phase 5 hardening pass. |
| OI-005 | Testing | medium | No committed Playwright E2E coverage exists and Chrome DevTools MCP is unavailable in this session. | Add browser journeys after dependencies and browser tooling are available. |
| OI-006 | Tooling | closed | The disposable `.venv` inside this worktree now contains `requirements.txt` dependencies and all 65 unit tests pass. | Keep the environment ignored; use it for local validation. |
| OI-007 | Observability | low | LangSmith upload attempts fail in restricted-network shells if hosted tracing is enabled through environment variables. | Keep tracing config safe; verify hosted traces only when network and credentials are intentionally available. |

## Phase Progress

| Phase | Status | Done | Issues/Notes |
|---|---|---|---|
| Phase 0 | complete | Source docs created; SQL subgraph restored; existing unit tests pass. | Working tree had deleted tracked modules; restored with stricter current tests. |
| Phase 1 | partial | Profile service, guardrail policy, local KB retriever, chat service facade, stdlib HTTP API, refreshed responsive static frontend shell, explicit client states, service/static contract tests, and local API smoke. | Browser interaction/accessibility test remains. |
| Phase 2 | complete | Markdown/PDF-source loader, deterministic chunker, chunk metadata writer, FAISS writer, ingestion report, FAISS hybrid retriever, lexical fallback, retrieval tests. | Metadata exists at `data/faiss/nexusone_chunks_metadata.jsonl`; FAISS index exists at `data/faiss/nexusone_chunks.index`. |
| Phase 3 | in-progress | Main LangGraph orchestrator added with load user, guardrail precheck, deterministic router, SQL subgraph route, RAG route, combined route, validation node, required final answer composition node, inline citation markers, source chunk payloads, combined citation+SQL source UI rendering, LangSmith-compatible run config, final response node, CLI runner, diagram, and tests. Frontend quality pass now provides profile context, responsive layout, accessible controls, and empty/loading/success/denied/no-answer/error-retry states. | Browser-level Playwright E2E coverage and live Postgres executor remain. |
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
