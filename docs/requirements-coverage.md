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
| R1 | Fake authentication/profile switching | partial | `app/auth/profiles.py` defines eight manifest-aligned sample profiles; `app/api/dev_server.py` exposes `/api/profiles`; `frontend/static/index.html` and `app.js` provide profile selection and reset the conversation on switch. | This is intentionally fake auth, not a session/authentication boundary. No browser/integration test proves switching changes the server response. |
| R2 | Role-aware chat UI | partial | Profile name, title, department, location, and role are visible in `frontend/static/index.html`; `app.js` sends the selected `user_id`; `tests/unit/services/test_chat_service.py` covers employee denial and CEO allowance at the service boundary. | No committed browser journey proves the visible role change and answer difference together. |
| R3 | Permission-aware document Q&A | partial | `app/retrieval/local_kb.py` and `app/retrieval/chunk_index.py` filter retrieval by profile; orchestrator retrieval is in `app/agents/orchestrator/nodes.py`; `tests/unit/services/test_local_kb.py` and `tests/unit/retrieval/test_chunk_index.py` cover permission filtering. | Full production permission-source integration and model-generation path are not proven; live Postgres is optional in the dev server. |
| R4 | Citations | partial | Orchestrator source refs include title, type, path, page/section where available, and updated date; `frontend/static/app.js` renders approved source cards and inline citation buttons; `tests/unit/frontend/test_static_chat_ui.py` covers the rendering contract. | Citation correctness is not evaluated end-to-end, and SQL source metadata is not a document citation. |
| R5 | Structured SQL connector | partial | `app/agents/sql_subgraph/` contains scope selection, allowlisted sources, read-only SQL validation, presentation sanitization, and repair-loop artifacts; `tests/unit/agents/sql_subgraph/` covers these pieces and the orchestrator routing tests cover SQL/combined routes. | The web server does not configure a live executor; live rows, retries, and DB integration are not consistently testable in this checkout. |
| R6 | Ticket status lookup | partial | Ticket intent routes to the SQL subgraph; safe ticket scope/presentation helpers are covered by `test_scope_selection.py`, `test_presentation.py`, and `test_graph_independent.py`. | The frontend cannot demonstrate live ticket statuses without Postgres; queue and ownership journeys lack browser/integration coverage. |
| R7 | Ticket creation | missing | The schema and `docs/phase4-ticket-actions-feedback-plan.md` describe the future service, but there is no ticket action service, write route, or orchestrator action node. | Phase 4 is pending. Do not imply that the ticket suggestion card creates a ticket. |
| R8 | Restricted-data refusal | partial | `app/guardrails/policy.py` performs server-side category checks; orchestrator denial happens before retrieval/SQL; `test_guardrail_policy.py`, `test_chat_service.py`, and `test_graph.py` assert safe denials without restricted titles. | Coverage is unit-level; no browser test checks that restricted text is absent from every client-visible surface. Heuristic classification is not a complete policy engine. |
| R9 | Prompt-injection resistance | partial | Prompt-injection patterns are classified and denied in `app/guardrails/policy.py`; guardrail, service, and graph tests cover bypass/escalation examples. | The pattern list is finite and there is no adversarial evaluation set or browser journey. |
| R10 | Feedback capture | missing | The database schema has a feedback table and the Phase 4 plan specifies an endpoint, but no `/api/feedback` handler or client submission exists. | Phase 4 is pending. No nonfunctional feedback controls were added to the refreshed UI. |
| R11 | Audit metadata | missing | `data/postgres/init/001_schema.sql` has an audit table and the plan defines safe fields; no service writes per-turn audit records. | Phase 4 is pending; no claim should be made from the schema alone. |
| R12 | Evaluation tests | partial | Guardrail, role-difference, retrieval, SQL validator, presentation, graph, ingestion, and static UI unit tests exist under `tests/unit/`. | There is no committed evaluation dataset, browser/E2E suite, retrieval-quality score, or systematic malicious/allowed matrix. |
| R13 | Responsive frontend | partial | `frontend/static/index.html`, `styles.css`, and `app.js` now provide a coherent desktop/mobile shell, profile context, empty, loading, success, denied, no-answer, error/retry states, keyboard submit, focus styling, reduced-motion support, and accessible labels. Static contracts are in `tests/unit/frontend/test_static_chat_ui.py`; local API/static smoke passed with `.venv`. | Browser inspection could not be completed because the Chrome DevTools MCP is unavailable; no Playwright evidence is committed. |
| R14 | Observability hooks | partial | `app/observability/langsmith.py` and orchestrator graph config provide safe LangSmith-compatible metadata/tags; `tests/unit/observability/test_langsmith.py` covers configuration. | Hosted trace delivery is environment/network dependent; token/cost/latency persistence and production dashboards are not implemented. |

## `docs/requirements.md` acceptance criteria

| Acceptance criterion | Status | Evidence | Remaining gap |
|---|---|---|---|
| Requirements and guardrails have traceable coverage | implemented | This audit plus `docs/agent-loop-status.md` and `docs/guardrails.md`. | The matrix will need updating as Phase 4/5 lands. |
| Backend authorization on every data/tool path | partial | Guardrail precheck in `app/agents/orchestrator/nodes.py`; SQL scope/validator/presentation tests; retrieval permission tests. | Ticket writes, feedback, audit writes, and a real DB-backed API path are not implemented/proven. |
| Restricted content blocked before retrieval/tool/model generation | partial | Graph denial tests assert retrieval/SQL nodes are absent; `test_graph.py` covers combined restricted questions. | No live model/tool integration test and no browser payload scan. |
| Authorized users receive useful cited answers | partial | Local KB/chunk retrieval, deterministic answer composition, graph tests, and static source rendering. | Live model/DB behavior and citation correctness are not fully verified. |
| SQL validates and repairs unsafe generated SQL | partial | `sql_validator.py`, SQL repair-loop graph artifacts, and validator/independent graph tests. | No live planner/executor integration run in this checkout. |
| Ticket creation/status flows work and are tested | partial for status, missing for creation | Status path has SQL subgraph tests; Phase 4 plan specifies creation but no implementation exists. | Creation and live status journeys remain. |
| UI is polished, responsive, accessible, and handles required states | partial | Refreshed static shell and frontend contract tests. | Browser/accessibility inspection and E2E are unavailable here. |
| Unit, integration, and Playwright journeys pass | partial | `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passes all 65 unit tests; `.venv` dependency setup and local `/api/profiles` + `/api/chat` smoke pass. | No committed integration/E2E config or browser journey; Playwright remains outstanding. |
| No secrets or real company data are committed | unverifiable | Profiles and generated data are explicitly synthetic; `.env.example` contains placeholders. | No secret-scanning command or policy test is configured. |

## Guardrail contract (`docs/guardrails.md`)

| Guardrail requirement | Status | Evidence | Gap |
|---|---|---|---|
| Resolve identity and role server-side | implemented | `app/auth/profiles.py`, `app/agents/orchestrator/nodes.py`, and unknown-user test in `test_chat_service.py`. | It is demo profile resolution, not real authentication. |
| Classify intent/data category before access | partial | Deterministic classifier and precheck in `app/guardrails/policy.py`; policy tests. | Classifier is keyword-based and not an exhaustive intent system. |
| Deny before retrieval, SQL, tools, or model calls | partial | Graph denial tests assert both retrieval and SQL are skipped; `test_graph.py`. | No action/tool path exists to verify; no live model call interception test. |
| Filter retrieval by role, group, user, department, confidentiality | implemented | `local_kb.py`, `chunk_index.py`, profiles/manifests, and retrieval tests. | Runtime PostgreSQL permission source is not exercised by the frontend server. |
| Use allowlisted SQL sources | implemented | `schema_registry.py`, permission scope modules, and `test_scope_selection.py`. | Live DB verification is environment-dependent. |
| Restrict SQL to one safe read-only statement | implemented | `sql_validator.py` and `test_sql_validator.py` cover DML/DDL/comments/multiple statements/hidden fields. | No live planner-to-executor test. |
| Sanitize rows/final output | implemented | `presentation.py`, `result_formatting.py`, `test_presentation.py`, and graph assertions for raw IDs. | More complete output fuzzing is still desirable. |
| Do not leak restricted titles, paths, snippets, or facts | partial | Denied service/graph tests assert known restricted titles are absent; frontend only renders backend-approved sources. | No systematic response-body/log/browser scan across all roles and indirect phrasings. |
| Log safe metadata only | missing | Schema and LangSmith-safe config exist. | Audit write service is not implemented. |
| Prompt injection is denied or safely redirected | partial | `_looks_like_prompt_injection`, policy/service/graph tests. | No broad adversarial test corpus. |

## PRD coverage (`nexusone_internal_ai_prd.md`)

| PRD area | Status | Evidence | Remaining gap |
|---|---|---|---|
| Six core product goals (Q&A, citations, role differences, tickets, ticket status, role-specific knowledge) | partial | RAG/SQL foundation and role/profile shell exist; ticket creation is absent. | Action workflows and live structured data are not complete. |
| Eight role profiles and role-specific access | partial | Eight synthetic profiles in `app/auth/profiles.py`; role matrix and policy tests. | No complete UI/API journey per role and manager/team scoping is incomplete. |
| Chat interface with follow-ups, citations, denial, ticket flows, feedback, identity | partial | Chat, profile identity, citation, denial, and follow-up-ready request loop exist in static app. | Ticket flows and feedback are missing; conversation persistence is absent. |
| PDF/Markdown/CSV/database source mix | partial | `data/docs` contains 34 PDFs, 37 Markdown files, and 20 CSVs; Postgres schema/seeds and FAISS sidecar exist. | Live structured-data behavior still depends on a running Postgres instance. |
| Document loading, chunking, embeddings, vector/BM25 hybrid, filtering, reranking, context packing | partial | Ingestion/chunking/index/retrieval modules and tests; FAISS index/metadata are present. | Reranking, BM25 parity, query rewriting, and full model context validation are not all implemented. |
| Agentic routing, decomposition, tool choice, clarification, refusal | partial | Deterministic main graph routes RAG/SQL/combined and validates outputs; guardrails refuse. | Decomposition, clarification, ticket tools, and general tool calling are missing. |
| Required tools (search/profile/permission/ticket/finance/directory/feedback) | partial | Profile, permission, retrieval, and constrained SQL portions exist. | Ticket creation, directory tool, finance tool API, and feedback tool are missing. |
| LLM gateway abstraction and model routing/usage tracking | partial | `answer_composer.py` has deterministic/OpenAI composition; LangSmith config exists. | A general provider gateway, routing matrix, usage/cost tracking, prompt versioning, and output schema gateway are not complete. |
| Guardrails and safe refusal | partial | Server-side policy, pre-retrieval checks, SQL validation, presentation sanitization, and tests. | Broad PII/tool misuse/unsupported-answer evaluation is pending. |
| Source citations with title/type/page-or-section/updated/link | partial | Backend citation payloads and frontend cards show title/type/path/page-or-section/updated when present. | No end-to-end citation evaluator; local path is not a clickable source link. |
| Feedback capture and audit logs | missing | Tables and plans only. | No API/service persistence. |
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
| Tool-augmented actions | missing | Ticket creation/action tools are Phase 4. |
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
| Demo readiness (role-difference questions, ticket creation/status, citations, ingestion report) | partial | Role-difference/denial and citation tests; ingestion outputs exist. | Ticket creation is missing; live status and browser demos are unverified. |
| Setup open decisions (embedding model, PDF method, BM25 library, SQL approach, CEO-only indexing, permission duplication) | needs-decision | The plan lists these as explicit open decisions; current implementation uses generated PDFs, local FAISS/lexical fallback, custom SQL graph, and duplicated manifest metadata. | Product/architecture authority should confirm whether to close these decisions before Phase 4/5. |

## Phase and context coverage

| Source / phase | Status | Evidence | Remaining gap |
|---|---|---|---|
| Phase 0 — repo contract/stabilization | implemented | Source docs, SQL package, and the full 65-test suite pass in the disposable `.venv`; compileall passes. | No remaining Phase 0 gap identified. |
| Phase 1 — service/frontend shell | partial | Profile service, guardrails, retrieval, dev API, refreshed static shell, focused tests, and local `/api/profiles`/`/api/chat` smoke. | Browser smoke/E2E and accessibility evidence remain. |
| Phase 2 — permission-aware RAG ingestion | partial | Loaders/chunking/FAISS sidecar/retrieval tests and generated index. | End-to-end model/DB permission path and full hybrid/rerank acceptance are not complete. |
| Phase 3 — main LangGraph orchestrator | partial | `app/agents/orchestrator/`, graph tests, combined route, validation/composition nodes, trace config, and all 65 unit tests passing in `.venv`. | Live executor and browser journey remain. |
| Phase 4 — ticket actions and feedback | missing | `docs/phase4-ticket-actions-feedback-plan.md` is a plan only; no action/feedback/audit modules. | Implement the planned services and tests before claiming R7/R10/R11. |
| Phase 5 — production hardening/E2E | missing | Phase plan only. | FastAPI adapter, Playwright journeys, accessibility checks, and production setup remain. |
| `PROJECT_CONTEXT.md` implementation claims | partial | Many listed modules/data artifacts exist; current frontend and orchestrator do match the described direction. | The document itself is historical and still describes pending work as future/current; use executable code and tests as authority. |
| `docs/agent-loop-status.md` | partial | It records current frontend, test, and dependency evidence and links back to this matrix. | It remains a rolling status file and must be updated as later phases land. |

## Validation snapshot for this audit

| Command/check | Result | Notes |
|---|---|---|
| `node --check frontend/static/app.js` | pass | Static JavaScript syntax check. |
| `git diff --check` | pass | No whitespace errors in the implementation diff. |
| Static HTTP asset smoke (`python -m http.server` + `curl`) | pass | HTML, CSS, and JavaScript assets served successfully and contained the new shell/state markers. |
| `python -m unittest tests.unit.frontend.test_static_chat_ui` | pass | 8 focused static frontend contract tests. |
| `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` | pass | All 65 tests pass in the disposable environment created from `requirements.txt`. |
| `python -m compileall app scripts` | pass | Python syntax/compile check. |
| Local API smoke (`.venv/bin/python scripts/run_web_app.py` + HTTP requests) | pass | 8 profiles loaded; employee AWS answer returned citations; employee Q4-risk request was denied without the restricted title; CEO Q4-risk request was accepted by the SQL route (`validated` without Postgres rows). |
| Browser/Playwright smoke | unverifiable | Chrome DevTools MCP is not available in this session; no Playwright config is committed. Static and API smoke ran separately. |

## Priority gaps

1. Implement Phase 4 ticket creation, feedback, and audit writes before presenting those workflows as product capabilities.
2. Add an integration/browser harness and keep its results separate from the passing unit suite.
3. Add Playwright coverage for profile switching, allowed/denied chat, mobile layout, loading, backend error/retry, and citation focus behavior.
4. Add a systematic evaluation matrix for role differences, indirect sensitive phrasing, prompt injection, and citation correctness.
5. Resolve the setup-plan open decisions with the product/architecture authority; preserve current defaults until then.
