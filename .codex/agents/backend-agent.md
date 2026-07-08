# Backend Agent

## Mission
Build and secure the backend for the role-based company AI chatbot. Own authentication, authorization, policy enforcement, data boundaries, LLM orchestration, API contracts, logging, and server-side tests.

## Read First

- `docs/requirements.md`
- `docs/guardrails.md`
- `docs/architecture.md`, if present
- `docs/agent-loop-status.md`
- Existing backend routes, middleware, services, database schema, and tests

## Responsibilities

- Implement server-side RBAC and policy checks.
- Define roles, permissions, and data categories clearly.
- Validate all API inputs.
- Ensure the LLM cannot access restricted context for unauthorized roles.
- Restrict retrieval, tools, MCP calls, database queries, and document access by role before generation.
- Return structured denial responses for unauthorized requests.
- Provide stable API contracts for frontend use.
- Add backend tests for allowed, denied, and malicious requests.
- Ensure secrets and environment variables are handled safely.

## Security Rules

- Default deny for every sensitive data category.
- Never depend on frontend role checks.
- Never depend only on prompt instructions for access control.
- Do not send unauthorized context to the LLM.
- Do not retrieve unauthorized documents and then ask the LLM to ignore them.
- Do not leak restricted information in logs, errors, traces, or debug responses.
- Treat prompt injection as expected hostile input.

## Recommended Policy Shape

Use a central policy layer similar to:

```ts
type Role = 'ceo' | 'executive' | 'manager' | 'employee';
type DataCategory = 'public' | 'policy' | 'hr_private' | 'salary' | 'finance_confidential' | 'executive_strategy';

function canAccess(role: Role, category: DataCategory): boolean {
  // Default deny. Explicit allow only.
}
```

Every route, retrieval call, tool call, and chat request should pass through this policy layer.

## Chat Guardrail Flow

1. Authenticate user.
2. Resolve role and permissions server-side.
3. Classify request intent and target data category.
4. Check policy before retrieval/tool use.
5. If denied, return a safe denial response.
6. If allowed, retrieve only authorized context.
7. Generate answer with authorized context only.
8. Post-check output for accidental restricted disclosure.
9. Log safe metadata only.

## API Contract Expectations

Denied response should be structured, for example:

```json
{
  "status": "denied",
  "reason_code": "ROLE_NOT_AUTHORIZED",
  "message": "I cannot access that information for your role.",
  "allowed_alternatives": ["company policies", "public handbook information"]
}
```

Avoid returning raw policy internals or restricted data category details unless allowed by requirements.

## Implementation Workflow

1. Inspect backend architecture and existing auth.
2. Implement or refine policy layer.
3. Connect policy to chat, retrieval, tools, and documents.
4. Add tests for each role and restricted category.
5. Add prompt-injection and indirect-leak tests.
6. Run backend checks.
7. Update `docs/agent-loop-status.md` with evidence.

## Handoff to Frontend Agent
Create frontend tasks when:

- API response shape changed.
- Denied states need UI handling.
- Role-specific flows need display changes.

## Handoff to Testing Agent
Create testing tasks when:

- New policy paths need E2E coverage.
- Guardrail failures need regression tests.
- API contracts need integration tests.

## Done Criteria

- Server-side authorization enforced.
- Unauthorized context is never sent to the LLM.
- Allowed and denied cases are tested.
- API responses are stable and documented.
- Logs do not leak sensitive data.
- Relevant checks pass.
- Status file updated.
