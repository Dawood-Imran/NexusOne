# NexusOne requirements coverage

## Audit scope and method

This audit was performed against the repository at the task branch after the frontend refresh. The inspected sources were:

- `docs/requirements.md` — the current requirement IDs (R1–R14) and acceptance criteria.
- `docs/guardrails.md` — the default-deny policy, role matrix, enforcement points, and SQL restrictions.
- `docs/implementation-phases.md` — phase exit criteria and the explicitly deferred Phase 4/5 work.
- `nexusone_internal_ai_prd.md` — product goals, use cases, tool/LLM/RAG requirements, and acceptance criteria.
- `nexusone_setup_data_plan.md` — source corpus, permission, SQL, FAISS, and demo-readiness targets.
- `PROJECT_CONTEXT.md`, `docs/agent-loop-status.md`, and `docs/phase4-ticket-actions-feedback-plan.md` — implementation claims, known drift, and planned action/feedback scope.
- Existing code and unit tests under `app/`, `frontend/static/`, and `tests/unit/`.

**Status meanings:** `implemented` means the behavior exists in code and has focused verification; `partial` means a meaningful safe slice exists but a contract, integration, or verification gap remains; `missing` means no product implementation exists; `unverifiable` means the repository does not provide enough executable evidence to make a claim. A route, stub, schema, or placeholder screen is not treated as completion.

The repository is a framework-independent local dev app. There is no `package.json`, npm script, Playwright config, or frontend build pipeline. The frontend is static HTML/CSS/JavaScript served by `app/api/dev_server.py`.

## Current requirement IDs (`docs/requirements.md`)

| ID | Requirement | Status | Concrete evidence | Gap / acceptance risk |
|---|---|---|---|---|
| R1 | Local username/password authentication | implemented | `app/auth/service.py`, `app/api/dev_server.py`, `docs/authentication.md`, and focused auth/API tests implement salted password verification, opaque server-side sessions, login/current-session/logout, and safe account details. | The local service is synthetic and not a production IdP. |
| R2 | Role-aware chat UI | partial | `app/api/dev_server.py` resolves role/profile from the authenticated session and rejects body identity changes; the static UI uses username/password auth, keeps the server-returned account immutable in the account popover, and omits client identity from chat/feedback bodies. | No committed browser journey proves the authenticated session and answer difference together.
| R3 | Permission-aware document Q&A | partial | `app/retrieval/local_kb.py` and `app/retrieval/chunk_index.py` filter retrieval by profile; orchestrator retrieval is in `app/agents/orchestrator/nodes.py`; `tests/unit/services/test_local_kb.py` and `tests/unit/retrieval/test_chunk_index.py` cover permission filtering. | Full production permission-source integration and model-generation path are not proven; live Postgres is optional in the dev server. |
| R4 | Citations | partial | Orchestrator source refs include title, type, path, page/section where available, and updated date; `frontend/static/app.js` renders approved source cards and inline citation buttons; `tests/unit/frontend/test_static_chat_ui.py` covers the rendering contract. | Citation correctness is not evaluated end-to-end, and SQL source metadata is not a document citation. |
| R5 | Structured SQL connector | partial | `app/agents/sql_subgraph/` contains scope selection, allowlisted sources, read-only SQL validation, presentation sanitization, and repair-loop artifacts; `ChatService` loads repository `.env`, injects a configured `DATABASE_URL` executor, and the frontend renders sanitized rows plus graph/subgraph traces. | Live rows and DB integration remain environment-dependent; disconnected mode is explicitly reported as validation-only.
| R6 | Ticket status lookup | partial | Ticket intent routes to the SQL subgraph; safe ticket scope/presentation helpers are covered by `test_scope_selection.py`, `test_presentation.py`, and `test_graph_independent.py`; configured web SQL responses expose sanitized rows and status metadata. | Queue and ownership journeys lack browser/integration coverage.
| R7 | Ticket creation | partial | `app/actions/ticket_service.py`, `app/agents/orchestrator/action_routing.py`, the `/api/chat` action path, and `tests/unit/actions/test_ticket_service.py`/`test_graph.py` implement deterministic IT/HR/Admin clarification and creation flows; the Phase 4 smoke script covers live writes. | Browser journey and durable end-to-end DB coverage remain; the UI only submits through the guarded service path. |
| R8 | Restricted-data refusal | partial | `app/guardrails/policy.py` performs server-side category checks; orchestrator denial happens before retrieval/SQL; `test_guardrail_policy.py`, `test_chat_service.py`, and `test_graph.py` assert safe denials without restricted titles. | Coverage is unit-level; no browser test checks that restricted text is absent from every client-visible surface. Heuristic classification is not a complete policy engine. |
| R9 | Prompt-injection resistance | partial | Prompt-injection patterns are classified and denied in `app/guardrails/policy.py`; guardrail, service, and graph tests cover bypass/escalation examples. | The pattern list is finite and there is no adversarial evaluation set or browser journey. |
| R10 | Feedback capture | partial | `app/actions/feedback_service.py`, `/api/feedback`, the static answer controls, `tests/unit/actions/test_feedback_service.py`, and the Phase 4 smoke script cover validated feedback persistence. | Browser journey and production auth boundary remain. |
| R11 | Audit metadata | partial | `app/actions/audit_service.py` and `app/services/chat_service.py` write safe redacted metadata; focused tests and the Phase 4 smoke script cover the service/repository path. | Production observability and browser/integration coverage remain. |
| R12 | Evaluation tests | partial | Guardrail, role-difference, retrieval, SQL validator, presentation, graph, ingestion, and static UI unit tests exist under `tests/unit/`. | There is no committed evaluation dataset, browser/E2E suite, retrieval-quality score, or systematic malicious/allowed matrix. |
| R13 | Responsive frontend | partial | `frontend/static/index.html`, `styles.css`, and `app.js` now provide a coherent desktop/mobile shell, immutable account popover, conversation structure, empty, loading, success, denied, no-answer, error/retry states, keyboard submit, auto-growing multiline composer, focus styling, reduced-motion support, and accessible labels. Static contracts are in `tests/unit/frontend/test_static_chat_ui.py`; `python3 -m unittest tests.unit.frontend.test_static_chat_ui`, `node --check frontend/static/app.js`, and chrome-devtools-axi desktop/mobile inspection pass. | A live auth-backed journey and committed E2E are not available. |
| R14 | Observability hooks | partial | `app/observability/langsmith.py` and orchestrator graph config provide safe LangSmith-compatible metadata/tags; `tests/unit/observability/test_langsmith.py` covers configuration. | Hosted trace delivery is environment/network dependent; token/cost/latency persistence and production dashboards are not implemented. |

## `docs/requirements.md` acceptance criteria

| Acceptance criterion | Status | Evidence | Remaining gap |
|---|---|---|---|
| Requirements and guardrails have traceable coverage | implemented | This audit plus `docs/agent-loop-status.md` and `docs/guardrails.md`. | The matrix will need updating as Phase 4/5 lands. |
| Backend authorization on every data/tool path | partial | Guardrail precheck in `app/agents/orchestrator/nodes.py`; SQL scope/validator/presentation tests; retrieval permission tests; guarded action routing and safe action/audit services. | Browser payload scans and a full production DB/API integration boundary remain. |
| Restricted content blocked before retrieval/tool/model generation | partial | Graph denial tests assert retrieval/SQL nodes are absent; `test_graph.py` covers combined restricted questions. | No live model/tool integration test and no browser payload scan. |
| Authorized users receive useful cited answers | partial | Local KB/chunk retrieval, deterministic answer composition, graph tests, and static source rendering. | Live model/DB behavior and citation correctness are not fully verified. |
| SQL validates and repairs unsafe generated SQL | partial | `sql_validator.py`, SQL repair-loop graph artifacts, and validator/independent graph tests. | No live planner/executor integration run in this checkout. |
| Ticket creation/status flows work and are tested | partial | Status path has SQL subgraph tests; ticket creation has deterministic action services, graph/API routing, focused unit coverage, and a live smoke script. | Browser journey and repeatable production DB integration remain. |
| UI is polished, responsive, accessible, and handles required states | partial | Refreshed static shell, authenticated account control/popover, auto-growing composer, conversation/source/trace inspector, frontend contract tests, and recorded desktop/mobile inspection evidence. | Live auth-backed accessibility journey and committed E2E remain. |
| Unit, integration, and Playwright journeys pass | partial | `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passes the integrated 96-test suite after installing `requirements.txt`; focused auth/API and frontend contracts pass separately. | No committed integration/E2E config or browser journey; Playwright remains outstanding.
| No secrets or real company data are committed | unverifiable | Profiles and generated data are explicitly synthetic; `.env.example` contains placeholders. | No secret-scanning command or policy test is configured. |

## Guardrail contract (`docs/guardrails.md`)

| Guardrail requirement | Status | Evidence | Gap |
|---|---|---|---|
| Resolve identity and role server-side | implemented | `app/auth/service.py`, `app/api/dev_server.py`, `app/auth/profiles.py`, and `tests/unit/api/test_dev_server_auth.py` resolve profile/role only from a server-owned session and reject identity tampering. | It is intentionally local synthetic authentication, not an external identity provider.
| Classify intent/data category before access | partial | Deterministic classifier and precheck in `app/guardrails/policy.py`; policy tests. | Classifier is keyword-based and not an exhaustive intent system. |
| Deny before retrieval, SQL, tools, or model calls | partial | Graph denial tests assert retrieval/SQL are skipped; action routing is separate and only runs after safe intent handling; `test_graph.py` and action tests cover the boundary. | No live model call interception test. |
| Filter retrieval by role, group, user, department, confidentiality | implemented | `local_kb.py`, `chunk_index.py`, profiles/manifests, and retrieval tests. | Runtime PostgreSQL permission source is not exercised by the frontend server. |
| Use allowlisted SQL sources | implemented | `schema_registry.py`, permission scope modules, and `test_scope_selection.py`. | Live DB verification is environment-dependent. |
| Restrict SQL to one safe read-only statement | implemented | `sql_validator.py` and `test_sql_validator.py` cover DML/DDL/comments/multiple statements/hidden fields. | No live planner-to-executor test. |
| Sanitize rows/final output | implemented | `presentation.py`, `result_formatting.py`, `test_presentation.py`, and graph assertions for raw IDs. | More complete output fuzzing is still desirable. |
| Do not leak restricted titles, paths, snippets, or facts | partial | Denied service/graph tests assert known restricted titles are absent; frontend only renders backend-approved sources. | No systematic response-body/log/browser scan across all roles and indirect phrasings. |
| Log safe metadata only | partial | `app/actions/audit_service.py`, chat service redaction, focused audit/service tests, and LangSmith-safe config. | Durable production telemetry and broader output fuzzing remain. |
| Prompt injection is denied or safely redirected | partial | `_looks_like_prompt_injection`, policy/service/graph tests. | No broad adversarial test corpus. |

## PRD coverage (`nexusone_internal_ai_prd.md`)

| PRD area | Status | Evidence | Remaining gap |
|---|---|---|---|
| Six core product goals (Q&A, citations, role differences, tickets, ticket status, role-specific knowledge) | partial | RAG/SQL foundation and role/profile shell exist; ticket creation is absent. | Action workflows and live structured data are not complete. |
| Eight role profiles and role-specific access | partial | Eight synthetic profiles in `app/auth/profiles.py`; role matrix and policy tests. | No complete UI/API journey per role and manager/team scoping is incomplete. |
| Chat interface with follow-ups, citations, denial, ticket flows, feedback, identity | partial | Chat, immutable server-session identity, profile-scoped conversation persistence, citations, denial, ticket actions, feedback, and conversation/source/rows/trace inspector metadata exist in the static app; `docs/authentication.md` defines the local contract. | Browser/E2E coverage and production hardening remain.
| PDF/Markdown/CSV/database source mix | partial | `data/docs` contains 34 PDFs, 37 Markdown files, and 20 CSVs; Postgres schema/seeds and FAISS sidecar exist. | Live structured-data behavior still depends on a running Postgres instance. |
| Document loading, chunking, embeddings, vector/BM25 hybrid, filtering, reranking, context packing | partial | Ingestion/chunking/index/retrieval modules and tests; FAISS index/metadata are present. | Reranking, BM25 parity, query rewriting, and full model context validation are not all implemented. |
| Agentic routing, decomposition, tool choice, clarification, refusal | partial | Deterministic main graph routes RAG/SQL/combined and validates outputs; guardrails refuse; action routing provides ticket clarification/creation. | General tool calling and decomposition remain. |
| Required tools (search/profile/permission/ticket/finance/directory/feedback) | partial | Profile, permission, retrieval, constrained SQL, ticket action, feedback, and audit services exist. | Directory/finance API adapters and production integration remain. |
| LLM gateway abstraction and model routing/usage tracking | partial | `answer_composer.py` has deterministic/OpenAI composition; LangSmith config exists. | A general provider gateway, routing matrix, usage/cost tracking, prompt versioning, and output schema gateway are not complete. |
| Guardrails and safe refusal | partial | Server-side policy, pre-retrieval checks, SQL validation, presentation sanitization, and tests. | Broad PII/tool misuse/unsupported-answer evaluation is pending. |
| Source citations with title/type/page-or-section/updated/link | partial | Backend citation payloads and frontend cards show title/type/path/page-or-section/updated when present. | No end-to-end citation evaluator; local path is not a clickable source link. |
| Feedback capture and audit logs | partial | Feedback and audit services, dev API routes, focused tests, and live Phase 4 smoke evidence. | Production auth/telemetry and browser journeys remain. |
| Evaluation dataset, RAG quality, groundedness, refusal, tool correctness | partial | Focused unit/regression tests. | No evaluation dataset or metrics. |
| Observability (latency, cost, tokens, retrieval, errors, feedback) | partial | Safe graph trace metadata and latency response fields. | No durable operational telemetry, cost/token tracking, or dashboard. |

### PRD RAG concept checklist

| Concept | Status | Evidence |
|---|---|---|
| Basic RAG | implemented | `app/retrieval/*`, orchestrator RAG route, retrieval/graph tests. |
| Hybrid search | partial | FAISS/metadata lexical path in `chunk_index.py`; full BM25 implementation/ranking evidence is limited. |
| Metadata filtering | implemented | Permission-aware chunk/local retrieval tests. |
| Role-based RAG | partial | Role-filtered retrieval and employee/CEO denial/allowance tests; no full answer comparison suite. |
| Agentic RAG | partial | LangGraph routes RAG/SQL/combined and validation; no full planner/tool loop. |
| Query rewriting | missing | No query rewriting component is wired. |
| Query decomposition | missing | No decomposition worker is wired. |
| Reranking | missing | No independent reranker component is wired. |
| Contextual compression | missing | No compression component is wired. |
| Source-aware answering | partial | Deterministic composer receives citations and frontend renders them. |
| Structured-data RAG | partial | Constrained SQL subgraph and source metadata exist; live web executor is not configured. |
| Tool-augmented actions | partial | Ticket action routing and deterministic ticket service are implemented and tested. | Broader tool catalog and live integration remain. |
| LLM gateway | partial | Answer composer/provider fallback exists, but not the full PRD gateway contract. |
| Evaluation | partial | Unit regression coverage only. |
| Observability | partial | Safe trace metadata and latency; no durable full telemetry. |

## Setup/data plan coverage (`nexusone_setup_data_plan.md`)

| Setup target | Status | Evidence | Gap |
|---|---|---|---|
| Corpus inventory and realistic synthetic source files | implemented | 34 PDFs, 37 Markdown KB files, 20 CSVs; manifests under `data/generated/manifests/`. | Generated corpus metadata is not validated by a single acceptance command. |
| PostgreSQL identity, permissions, documents, tickets, business, audit, feedback schema | partial | `docker-compose.yml`, `data/postgres/init/001_schema.sql`, seed scripts, and permission-safe views. | Runtime DB is optional for the web app and audit/feedback writes are absent. |
| FAISS PDF/Markdown index and metadata sidecar | implemented | `data/faiss/nexusone_chunks.index`, `nexusone_chunks_metadata.jsonl`, `scripts/build_rag_index.py`, ingestion tests, and local `/api/chat` allowed/denied smoke. | No browser retrieval journey is committed. |
| Constrained SQL connector and exact structured queries | partial | SQL subgraph modules, allowlisted schema, validator, presentation, and unit tests. | Live Postgres executor and integration test are environment-dependent. |
| Permission success criteria for employee/manager/HR/finance/IT/CEO and explicit/group grants | partial | Role/profile manifests, guardrail policy, retrieval and SQL scope tests. | Not every role/category/source combination has a regression test; some PRD scope is deferred. |
| Demo readiness (role-difference questions, ticket creation/status, citations, ingestion report) | partial | Role-difference/denial, citation, ticket action, feedback, audit, and ingestion tests/smokes exist. | Live status and browser demos are unverified. |
| Setup open decisions (embedding model, PDF method, BM25 library, SQL approach, CEO-only indexing, permission duplication) | needs-decision | The plan lists these as explicit open decisions; current implementation uses generated PDFs, local FAISS/lexical fallback, custom SQL graph, and duplicated manifest metadata. | Product/architecture authority should confirm whether to close these decisions before Phase 4/5. |

## Phase and context coverage

| Source / phase | Status | Evidence | Remaining gap |
|---|---|---|---|
| Phase 0 — repo contract/stabilization | implemented | Source docs, SQL package, and the integrated 105-test suite pass in the disposable `.venv`; compileall passes. | No remaining Phase 0 gap identified. |
| Phase 1 — service/frontend shell | partial | Profile service, guardrails, retrieval, authenticated dev API, refreshed static shell, focused tests, and local auth/chat smoke. | Committed browser E2E and production hardening remain. |
| Phase 2 — permission-aware RAG ingestion | partial | Loaders/chunking/FAISS sidecar/retrieval tests and generated index. | End-to-end model/DB permission path and full hybrid/rerank acceptance are not complete. |
| Phase 3 — main LangGraph orchestrator | partial | `app/agents/orchestrator/`, graph tests, combined route, validation/composition nodes, trace config, and the integrated unit suite passing in `.venv`. | Live executor and browser journey remain.
| Phase 4 — ticket actions and feedback | in-progress | Deterministic ticket actions, feedback, audit metadata, graph/API routes, static controls, focused tests, and live smoke script are present on the integrated line. | Repeatable browser E2E and production hardening remain. |
| Phase 5 — production hardening/E2E | missing | Phase plan only. | FastAPI adapter, Playwright journeys, accessibility checks, and production setup remain. |
| `PROJECT_CONTEXT.md` implementation claims | partial | Many listed modules/data artifacts exist; current frontend and orchestrator do match the described direction. | The document itself is historical and still describes pending work as future/current; use executable code and tests as authority. |
| `docs/agent-loop-status.md` | partial | It records current frontend, test, and dependency evidence and links back to this matrix. | It remains a rolling status file and must be updated as later phases land. |

## Validation snapshot for this audit

| Command/check | Result | Notes |
|---|---|---|
| `node --check frontend/static/app.js` | pass | Static JavaScript syntax check. |
| `git diff --check` | pass | No whitespace errors in the implementation diff. |
| Static HTTP asset smoke (`python -m http.server` + `curl`) | pass | HTML, CSS, and JavaScript assets served successfully and contained the new shell/state markers. |
| `.venv/bin/python -m unittest tests.unit.frontend.test_static_chat_ui` | pass | 13 focused static frontend contract tests after integration. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | The integrated 105-test suite passes in the disposable environment created from `requirements.txt`. |
| `python -m compileall app scripts` | pass | Python syntax/compile check. |
| Local API smoke (`.venv/bin/python scripts/run_web_app.py` + HTTP requests) | pass | Auth/session/logout, server-owned chat, identity tampering rejection, employee AWS citations, employee Q4-risk denial, structured response/trace shape, feedback, and static assets verified; isolated worktree had no repository `.env`, so OpenAI/Postgres live paths were not exercised. |
| chrome-devtools-axi browser smoke | pass | Authenticated desktop workspace, account popover, cited answer/source inspector, capability reporting, and 390x844 responsive layout verified; no committed Playwright config exists. |

## Priority gaps

1. Add a committed integration/browser harness and keep its results separate from the passing unit suite; the local chrome-devtools-axi smoke is manual only.
2. Harden the production API/auth boundary and repeat the Phase 4 DB integration checks in CI.
3. Add Playwright coverage for profile switching, allowed/denied chat, mobile layout, loading, backend error/retry, and citation focus behavior.
4. Add a systematic evaluation matrix for role differences, indirect sensitive phrasing, prompt injection, and citation correctness.
5. Resolve the setup-plan open decisions with the product/architecture authority; preserve current defaults until then.
