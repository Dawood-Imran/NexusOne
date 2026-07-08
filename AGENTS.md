# AGENTS.md

This repository is built by a Codex multi-agent loop for a role-based company AI chatbot.

## Source of Truth
Read these before changing code:

1. `docs/requirements.md`
2. `docs/guardrails.md`
3. `docs/agent-loop-status.md`
4. Existing tests and app structure

When requirements conflict with implementation, update implementation. When requirements are ambiguous, document the assumption in `docs/agent-loop-status.md` and implement the safest reasonable behavior.

## Product Standard
The product must feel like a professional company web application, not an AI-generated demo. UI must be clean, intentional, responsive, accessible, and complete across loading, empty, error, permission-denied, and success states.

## Security Standard
Role-based access control must be enforced server-side. Frontend visibility controls are not sufficient. Any restricted data must be blocked before model generation or tool/retrieval access whenever possible.

## Guardrail Principle
Default deny. A role may access a data category only if `docs/guardrails.md` explicitly allows it.

## Required Commands
Use the commands defined by the repo. If package scripts exist, prefer them:

```bash
npm run lint
npm run typecheck
npm run test
npm run test:e2e
npm run build
```

If commands differ, inspect `package.json`, backend config, and test config, then document the actual commands in `docs/agent-loop-status.md`.

## Required Workflow

1. Inspect requirements and current implementation.
2. Identify the smallest useful change.
3. Implement with tests.
4. Run relevant checks.
5. Update `docs/agent-loop-status.md`.
6. Continue until final acceptance is reached.

## Agent Files
Specialized agent instructions are stored in:

- `.codex/agents/frontend-agent.md`
- `.codex/agents/backend-agent.md`
- `.codex/agents/testing-agent.md`

## Skill Files
Reusable review instructions are stored in:

- `.codex/skills/ui-professional-design/SKILL.md`
- `.codex/skills/ux-product-review/SKILL.md`

Use them whenever working on interface quality, product usability, or Playwright-driven UX review.
