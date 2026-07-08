# NexusOne Implementation Phases

## Phase 0: Repo Contract and Stabilization

Goal: make the repo internally consistent and restore the backend foundation expected by tests.

Planned work:

- Create missing `docs/requirements.md`, `docs/guardrails.md`, and `docs/agent-loop-status.md`.
- Restore the independent SQL subgraph package.
- Keep SQL source selection, validation, repair, and presentation modular.
- Run existing unit tests.

Exit criteria:

- Existing SQL subgraph tests pass.
- Status file records current drift and resolved gaps.

## Phase 1: Backend Service and Frontend Shell

Goal: provide a runnable app loop with fake auth, guarded chat, citations, and visible role context.

Planned work:

- Add framework-independent profile, guardrail, retrieval, and chat service modules.
- Add a small stdlib dev HTTP server for `/api/profiles` and `/api/chat`.
- Add a static frontend chat shell with role switching, loading, denied, error, success, source, and trace states.
- Add unit tests for service-level guardrails and retrieval permissions.
- Use Playwright MCP to inspect the running app after implementation.

Exit criteria:

- Frontend can load from local server.
- Employee can ask allowed KB questions.
- Employee restricted finance/executive request is denied without leaked restricted content.
- CEO/executive request is not denied by pre-policy.
- Relevant unit tests pass.

## Phase 2: Permission-Aware RAG Ingestion

Goal: ingest Markdown and PDF sources into a local searchable knowledge layer.

Planned work:

- Parse Markdown and PDFs into chunks with metadata.
- Store chunk metadata in PostgreSQL.
- Build FAISS index for PDFs/Markdown only.
- Add keyword/BM25 fallback.
- Enforce permission filters before context packing.
- Add citation and no-answer tests.

Exit criteria:

- Retrieval returns only authorized chunks.
- Same question differs by role where required.
- Citations include title/source/page or section/updated date.

## Phase 3: Main LangGraph Orchestrator

Goal: connect routing, RAG, SQL connector, tool flows, validation, and answer generation.

Planned work:

- Build main graph with deterministic routing gates.
- Route structured exact-data questions to the SQL subgraph.
- Route policy/document questions to RAG.
- Support combined SQL + RAG questions.
- Add evaluator/grounding and permission post-check nodes.
- Add LangSmith-compatible trace hooks.

Exit criteria:

- Graph traces show route, permissions, retrieval/tool calls, validation, and final status.
- Combined questions can use multiple subgraphs safely.

## Phase 4: Ticket Actions and Feedback

Goal: make the assistant action-capable.

Detailed plan: `docs/phase4-ticket-actions-feedback-plan.md`.

Planned work:

- Add ticket creation flow for HR, IT, and Admin.
- Validate required fields and ask clarifying questions.
- Persist tickets and ticket events.
- Add feedback submission API and storage.
- Add audit log writes.

Exit criteria:

- Users can create tickets.
- Users can check own tickets.
- Queue roles can view allowed queues.
- Feedback and audit metadata are stored safely.

## Phase 5: Production Hardening and E2E Acceptance

Goal: make the app portfolio-grade.

Planned work:

- Replace dev server adapter with FastAPI once dependencies are installed.
- Add Playwright E2E journeys across roles and mobile/desktop.
- Add accessibility and responsive checks.
- Add injection and restricted-data regression tests.
- Add setup README and final architecture docs.

Exit criteria:

- Lint/type/test/build/E2E commands pass or documented equivalents pass.
- UI/UX review passes.
- Requirements and guardrails coverage are complete.
