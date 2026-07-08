# NexusOne Copilot Requirements

## Product Goal

NexusOne Copilot is a permission-aware internal AI assistant for the fictional company NexusOne Technologies. It must answer company questions, route structured-data requests, create or inspect support tickets, show citations where source material is used, and enforce role-based access before any restricted data reaches a model, tool, API response, or UI.

## Initial Roles

| Role | Core Access |
|---|---|
| employee | Public/internal company policies, public KB, own tickets. |
| manager | Employee access plus manager process docs and team-oriented guidance. |
| hr | HR policies, HR queue/process docs, HR-sensitive operational docs. |
| finance | Finance policy, finance summaries, budget/vendor/payment data allowed to finance. |
| it_admin | IT support KB, device/security docs, IT ticket queue. |
| admin_ops | Admin/facilities docs and admin ticket queue. |
| executive | Executive reports, strategy summaries, risk docs except CEO-only. |
| ceo | Executive access plus CEO-only docs. |

## Functional Requirements

| ID | Requirement | Notes |
|---|---|---|
| R1 | Fake authentication/profile switching | Use sample users from the NexusOne manifests. |
| R2 | Role-aware chat UI | The selected user profile must be visible and must affect answers. |
| R3 | Permission-aware document Q&A | Retrieve only documents/chunks allowed for the current user. |
| R4 | Citations | Knowledge answers should include title, source type/path, and updated date where known. |
| R5 | Structured SQL connector | Exact data questions should route to a constrained SQL subgraph. |
| R6 | Ticket status lookup | Users can view own tickets; queue roles can view their allowed queues. |
| R7 | Ticket creation | Chat flow should collect required details and create HR/IT/Admin tickets. |
| R8 | Restricted-data refusal | Unauthorized users receive a calm denial without leaked titles, paths, snippets, or facts. |
| R9 | Prompt-injection resistance | Role escalation and instruction override attempts must be denied or ignored safely. |
| R10 | Feedback capture | Users can mark answers helpful/not helpful and report issues. |
| R11 | Audit metadata | Log safe metadata for user, intent, access decision, sources/tools, latency, and status. |
| R12 | Evaluation tests | Include allowed, denied, malicious, and role-difference test cases. |
| R13 | Responsive frontend | Desktop and mobile views must support loading, empty, success, denied, and error states. |
| R14 | Observability hooks | LangSmith-compatible tracing should be planned for agent/model phases. |

## Current Implementation Scope

Phase 0 and Phase 1 focus on a safe foundation:

- Source-of-truth docs.
- Restored independent SQL subgraph.
- Framework-independent chat service.
- Minimal dev HTTP API.
- Static professional chat UI.
- Unit tests for guardrails, retrieval permissions, and SQL behavior.

Full FAISS ingestion, LLM final-answer generation, ticket creation persistence, LangSmith tracing, and Playwright E2E hardening are later phases.

## Acceptance Criteria

The application is complete only when:

- Requirements and guardrails have traceable coverage in `docs/agent-loop-status.md`.
- Backend authorization is enforced server-side for every data/tool path.
- Restricted content is blocked before retrieval/tool execution/model generation.
- Authorized users receive useful, cited answers.
- SQL connector validates and repairs unsafe generated SQL before execution.
- Ticket creation/status flows work and are tested.
- UI is polished, responsive, accessible, and handles empty/loading/error/denied/success states.
- Unit, integration, and Playwright journeys pass.
- No secrets or real company data are committed.
