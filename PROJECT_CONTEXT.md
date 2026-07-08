# NexusOne Copilot Project Context

## Current Goal

Build NexusOne Copilot, a permission-aware internal AI assistant for a fictional company, NexusOne Technologies.

The project has moved from data setup into the app implementation loop. Phase 0 restored the backend SQL subgraph foundation and created the missing source-of-truth docs. Phase 1 added a framework-independent backend service layer, stdlib dev HTTP server, static frontend shell, and guardrail/retrieval service tests. Phase 2 is now complete with permission-carrying chunk metadata plus a FAISS hybrid retrieval path. Phase 3 is in progress with a main LangGraph orchestrator that routes between guardrails, RAG, SQL, combined questions, validation, required final answer composition with inline citations, and final response packaging.

The detailed phase tracker is now `docs/agent-loop-status.md`.

## Source Documents

- `nexusone_internal_ai_prd.md` - Product requirements document.
- `nexusone_setup_data_plan.md` - Setup, data source, permissions, PostgreSQL, FAISS, and success criteria plan.
- `docs/requirements.md` - Current implementation requirements distilled from the PRD.
- `docs/guardrails.md` - Role and data-access guardrail contract.
- `docs/implementation-phases.md` - Phase plan for the app build.
- `docs/agent-loop-status.md` - Current loop status, test evidence, open issues, and phase progress.
- `PROJECT_CONTEXT.md` - This global project status/context file.

## Architecture Direction

The main app should use a custom routed LangGraph workflow.

Pattern mix:

- Main workflow: custom routed workflow.
- Intent handling: routing workflow.
- Retrieval: FAISS hybrid search plus metadata lexical fallback.
- Complex executive/manager comparisons: orchestrator-worker subflow.
- Final answer checks: bounded evaluator/validator gate.
- Tickets and structured data: controlled tool calls.

Reason:

NexusOne has strict permission requirements. A fully open-ended agent loop would be too risky because tool and retrieval decisions must be auditable and constrained. The graph should make permission checks explicit before retrieval, after retrieval, before tool execution, and before final answer.

## Completed So Far

- App/data/docs/frontend/test folder scaffold has been created.
- The setup/data plan has been written.
- A single global context file now tracks project status and next steps.
- First-pass source manifests have been created for users, groups, permissions, documents, and CSV sources.
- Markdown KB source files have been generated from `data/generated/manifests/documents.yaml`.
- CSV seed/source files have been generated from `data/generated/manifests/csv_sources.yaml`.
- PDF source documents have been generated from `data/generated/manifests/documents.yaml`.
- Docker Compose for local PostgreSQL has been added.
- Initial PostgreSQL schema has been added under `data/postgres/init/001_schema.sql`.
- PostgreSQL seed scripts have been added and loaded into the local Docker database.
- A visual LangGraph architecture graph has been created under `docs/architecture/graph.svg`.
- An independent SQL subgraph package has been added under `app/agents/sql_subgraph`.
- Permission-safe SQL helpers have been added under `data/postgres/init/005_permission_safe_views.sql`.
- Standard-library unit tests now cover SQL source selection, SQL validation, and standalone SQL subgraph invocation.
- LangChain OpenAI planning support has been added through `app/agents/sql_subgraph/planner.py`.
- `scripts/run_sql_subgraph.py` can run the SQL subgraph independently against local Postgres.
- `scripts/sql_subgraph_chatbot.py` can run an interactive terminal chatbot with node-by-node trace output.
- `requirements.txt` and `.env.example` now document the LangChain/OpenAI/Postgres runtime setup.

Current scaffold summary:

```text
app/
  api/
  agents/
  auth/
  core/
  db/
  evaluation/
  gateway/
  guardrails/
  ingestion/
  models/
  observability/
  retrieval/
  schemas/
  services/
  tools/
  utils/
data/
  docs/
    pdf/
    markdown_kb/
    csv/
  generated/
    manifests/
    ingestion_reports/
  faiss/
  postgres/
docs/
  architecture/
  data/
  setup/
frontend/
tests/
scripts/
```

## Current Task

Continue Phase 2 and then move into the main LangGraph orchestrator.

Phase 1 current state:

- `app/auth/profiles.py` provides fake profile switching data.
- `app/guardrails/policy.py` enforces pre-retrieval role denials and prompt-injection handling.
- `app/retrieval/local_kb.py` provides permission-aware Markdown KB retrieval with citations.
- `app/retrieval/chunk_index.py` reads generated chunk metadata and provides permission-aware metadata-backed retrieval across Markdown and PDF-source chunks.
- `app/agents/orchestrator/` contains the main LangGraph workflow for user loading, guardrail precheck, deterministic routing, SQL subgraph calls, RAG retrieval, answer validation, and final response packaging.
- RAG answers now include inline source markers such as `[1]`, and citation payloads include the permitted source chunk text for frontend source cards.
- Graph invocations now attach LangSmith-compatible run config with safe metadata, tags, and run names while excluding message text, final answers, SQL text, and source chunks from metadata.
- `app/services/chat_service.py` delegates chat requests to the main orchestrator while keeping the frontend/API response contract stable.
- `app/api/dev_server.py` exposes `/api/profiles` and `/api/chat` through a stdlib HTTP server.
- `frontend/static/` contains the current static frontend shell. Combined SQL+RAG answers now render both document citations and SQL source metadata instead of hiding SQL sources when citations exist.
- `tests/unit/services/` covers guardrail policy, local KB permissions, and chat service behavior.

Latest verification:

- `./venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passed with 61 tests.
- `./venv/bin/python -m compileall app scripts` passed.
- `./venv/bin/python -m unittest tests.unit.agents.orchestrator.test_graph tests.unit.frontend.test_static_chat_ui tests.unit.services.test_chat_service` passed with 14 focused Phase 3 tests.
- `./venv/bin/python scripts/build_rag_index.py` wrote 106 chunks from 71 documents and generated `data/faiss/nexusone_chunks.index` with `faiss_status=written`.
- `./venv/bin/python scripts/run_orchestrator.py --user-id u001 --execute-sql "What holidays apply in Pakistan?"` returned 3 live Postgres holiday rows when run outside the sandbox.
- Local `/api/chat` smoke test returned `From AWS Access Request [1]:` and citation `[1]` included the AWS chunk text containing the ticket request step.
- CLI combined SQL+RAG smoke returned `citations` and SQL `sources`; hosted LangSmith upload failed because this shell has tracing enabled but network access is restricted, while graph execution still completed successfully.
- Initial Playwright MCP page load succeeded on `http://127.0.0.1:8010`; final restart was blocked by sandbox approval timeout and is recorded in `docs/agent-loop-status.md`.

Next implementation step:

Continue Phase 3 with broader combined SQL+RAG/E2E coverage, then move into Phase 4 ticket actions/feedback.

SQL repair-loop graph artifacts:

- Plan: `app/agents/sql_subgraph/SQL_REPAIR_LOOP_IMPLEMENTATION_PLAN.md`
- LangGraph visualization builder: `app/agents/sql_subgraph/langgraph_visualization.py`
- Render script: `scripts/render_sql_subgraph_graph.py`
- PNG: `docs/graphs/sql_repair_subgraph.png`
- Mermaid source: `docs/graphs/sql_repair_subgraph.mmd`

Ticket assignment policy:

- Raw `assigned_to`, `requester_id`, and other user id fields remain hidden and validator-blocked.
- User-facing assignee names are allowed only through `accessible_ticket_assignments(:user_id)`, which first applies `can_user_access_ticket`.
- Assignment questions such as "who is assigned to IT-1046" or "who is handling IT-1046" use the safe assignment function and return display name/title/department when the ticket is accessible.
- Terminal escape artifacts from arrow keys are stripped before routing/query generation.
- If the ticket is not accessible, the answer is "I could not find an accessible matching ticket."

The manifests remain the source of truth for:

- Fake users and role profiles.
- Groups and group membership.
- Planned PDF, Markdown, and CSV sources.
- Document permissions.
- Future PostgreSQL seed data.
- Future FAISS chunk metadata.

## Manifest Files

Created under `data/generated/manifests/`:

- `users.yaml`
- `groups.yaml`
- `documents.yaml`
- `permissions.yaml`
- `csv_sources.yaml`

These are not generated company documents yet. They describe what will be generated next.

## Generated Markdown KB Files

Created under `data/docs/markdown_kb/`:

- 6 public/internal KB files.
- 6 IT KB files.
- 5 HR KB files.
- 4 manager KB files.
- 4 engineering KB files.
- 4 Admin KB files.
- 4 Finance KB files.
- 4 Executive/CEO KB files.

All 37 Markdown files include front matter with `doc_id`, `source_path`, `department`, `permission_profile`, `confidentiality`, allowed roles, allowed groups, allowed users, `updated_at`, and generation metadata.

## Generated CSV Files

Created under `data/docs/csv/`:

- 8 public/setup CSV files for holidays, tools, offices, users, groups, departments, and public project status.
- 4 ticket seed CSV files for IT, HR, Admin, and Finance queues.
- 4 Finance CSV files for Q4 summary, department budgets, revenue risks, and vendor aging.
- 3 HR CSV files for benefits vendors, headcount plan, and lifecycle SLA.
- 1 Executive CSV file for restricted project status risks.

All 20 CSV files use the headers listed in `data/generated/manifests/csv_sources.yaml`. The data is fictional and designed to test public lookup, SQL-only ticket access, restricted finance retrieval, HR restrictions, manager access, executive access, and employee-vs-CEO differences.

## Generated PDF Files

Created under `data/docs/pdf/`:

- 8 public/internal PDF files.
- 5 manager PDF files.
- 5 HR PDF files.
- 5 IT PDF files.
- 5 Finance PDF files.
- 6 Executive/CEO PDF files.

Also created `scripts/generate_pdf_sources.py` and reviewable Markdown sources under `data/generated/pdf_sources/`. The generator reads the document and permission manifests, writes Markdown source copies, then renders dependency-free PDF files with document control metadata and page numbers.

## PostgreSQL Docker Setup

Created:

- `docker-compose.yml`
- `data/postgres/init/README.md`
- `data/postgres/seeds/README.md`

The Compose setup uses:

- Image: `postgres:16`
- Database: `nexusone`
- User: `nexusone`
- Demo password: `nexusone_dev_password`
- Port mapping: `5492:5432`
- Data volume: `nexusone_postgres_data`
- Init mount: `./data/postgres/init:/docker-entrypoint-initdb.d:ro`
- Healthcheck: `pg_isready -U nexusone -d nexusone`

## PostgreSQL Schema

Created `data/postgres/init/001_schema.sql`.

The schema includes:

- Identity tables: users, groups, user groups, departments, employee directory.
- Permission tables: permission profiles, permission profile grants, document permissions.
- Document/RAG tables: documents, document chunks, ingestion runs.
- Ticket tables: tickets and ticket events.
- Public lookup tables: company holidays, tool directory, office locations.
- Finance tables: finance summaries, department budgets, revenue risks, vendor payment aging.
- HR/Admin/Project tables: benefits vendors, headcount plan, lifecycle SLA, public project status, executive project status.
- Observability tables: audit logs and feedback.
- Validation helpers: `can_user_access_document`, `can_user_access_ticket`, and `user_accessible_documents`.

## PostgreSQL Seeds

Created:

- `scripts/generate_postgres_manifest_seeds.py`
- `data/postgres/init/002_seed_permission_profiles.sql`
- `data/postgres/init/003_load_csv_sources.sql`
- `data/postgres/init/004_seed_documents_and_permissions.sql`

Updated `docker-compose.yml` to mount generated CSV files into the Postgres container at `/seed/csv`.

Loaded into the local `nexusone_postgres` container:

- 8 users.
- 13 groups.
- 28 user group memberships.
- 91 document metadata records: 34 PDFs, 37 Markdown files, 20 CSV sources.
- 606 document permission grants.
- 20 tickets and 20 ticket events.
- Finance, HR, Admin, IT, office, holiday, tool, and project seed tables.

Validated examples:

- Employee `u001` cannot access `q4-revenue-risk-register-2025`.
- CEO `u006` can access `q4-revenue-risk-register-2025`.
- Manager `u002` can access `hiring-request-process-2026`.
- Employee `u001` cannot access `hiring-request-process-2026`.
- Employee `u001` cannot access CEO-only acquisition notes.
- CEO `u006` can access CEO-only acquisition notes.
- Employee `u001` can access own IT ticket `IT-1042`.
- HR user `u003` can access sensitive HR ticket `HR-2034`.

## Key Runtime Rules

The implementation must enforce:

1. A user can access public/internal documents.
2. A user can access documents allowed for their role.
3. A user can access documents allowed for one of their groups.
4. A user can access documents explicitly shared with their user id.
5. Employees can only see their own tickets.
6. HR, IT, Admin, and Finance roles can see their department queues.
7. Restricted document titles, paths, snippets, and facts must not be revealed to unauthorized users.
8. Permissions must be checked before retrieval, after retrieval, before tool execution, and before final answer.

## Current Technical Decisions

- PostgreSQL will run through Docker.
- FAISS will be used as the first vector index.
- PostgreSQL is the runtime source of truth for permissions.
- Manifest files duplicate permission metadata for generation and validation.
- CSVs and tickets should stay in PostgreSQL for the first version, not FAISS.
- Structured CSV/PostgreSQL questions should use a constrained SQL connector/tool.
- The SQL connector should be implemented as a custom constrained LangGraph SQL subgraph with deterministic validation, not as an unrestricted prebuilt SQL agent.
- SQL subgraph final answers must pass through a presentation/sanitization layer. Raw user-reference fields such as requester IDs, assignee IDs, actor IDs, manager IDs, owner IDs, SQL, SQL parameters, source paths, and confidentiality labels are internal debug data and should not appear in normal user-facing answers.
- Terminal node traces are hidden by default. When enabled with `--show-nodes` or `/trace on`, traces are sanitized and should show node status, intent, source names, parameter keys, validation status, row counts, and elapsed time, not raw SQL or parameter values.
- PDF and Markdown sources should use ingestion, chunking, FAISS, and BM25.
- At least one CEO-only document should exist to test strict refusal behavior.

## Open Decisions

These still need to be finalized:

1. Embedding model: local sentence-transformer or API embedding model.
2. PDF generation method: Markdown-to-PDF, HTML-to-PDF, or Python reportlab.
3. BM25 implementation: `rank-bm25`, Whoosh, or custom lightweight keyword index.
4. Whether CEO-only M&A notes should be embedded into FAISS or kept out of vector search.

Recommended defaults from the setup plan:

1. Use a local embedding model first if available.
2. Generate PDFs from Markdown/HTML templates.
3. Use `rank-bm25` for the first local keyword search implementation.
4. Keep CSVs and tickets in PostgreSQL only for the first version.
5. Build a custom constrained LangGraph SQL subgraph for exact structured data.
6. Include one CEO-only document for strict permission testing.

## Next Steps

Immediate next step:

1. Export `OPENAI_API_KEY` or create `.env` from `.env.example`.
2. Run the terminal chatbot with `./venv/bin/python scripts/sql_subgraph_chatbot.py --user-id u001`.
3. Run additional permission checks for employee, finance, executive, and CEO users.
4. Then add ingestion pipeline for PDFs and Markdown only.

After SQL connector and ingestion:

1. Add FAISS index builder.
2. Add validation script for permissions, SQL, and retrieval.

## Move-To-Implementation Criteria

We should not start the full app implementation until:

- Source manifests exist.
- Fake source files are generated.
- PostgreSQL schema and seed data exist.
- FAISS index can be built.
- Manual validation can prove employee vs CEO permission differences.
- Ticket ownership checks work.
- Source citations can be produced for PDF pages and Markdown sections.
