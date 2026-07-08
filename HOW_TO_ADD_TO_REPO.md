# How to Add These Files to Your Current Repo

From your project root, copy the generated files into the same relative paths:

```bash
cp AGENTS.md ./AGENTS.md
mkdir -p .codex/agents
mkdir -p .codex/skills/ui-professional-design
mkdir -p .codex/skills/ux-product-review
cp .codex/agents/frontend-agent.md ./.codex/agents/frontend-agent.md
cp .codex/agents/backend-agent.md ./.codex/agents/backend-agent.md
cp .codex/agents/testing-agent.md ./.codex/agents/testing-agent.md
cp .codex/skills/ui-professional-design/SKILL.md ./.codex/skills/ui-professional-design/SKILL.md
cp .codex/skills/ux-product-review/SKILL.md ./.codex/skills/ux-product-review/SKILL.md
cp ORCHESTRATOR_PROMPT.md ./ORCHESTRATOR_PROMPT.md
```

If you are copying from this package manually, preserve this structure:

```txt
AGENTS.md
ORCHESTRATOR_PROMPT.md
HOW_TO_ADD_TO_REPO.md
.codex/
  agents/
    frontend-agent.md
    backend-agent.md
    testing-agent.md
  skills/
    ui-professional-design/
      SKILL.md
    ux-product-review/
      SKILL.md
```

## Required Docs To Add Or Verify

Create these files if they do not already exist:

```txt
docs/requirements.md
docs/guardrails.md
docs/agent-loop-status.md
```

Recommended optional docs:

```txt
docs/architecture.md
docs/ui-ux.md
```

## How To Use In Codex

1. Open Codex in the repo.
2. Paste the contents of `ORCHESTRATOR_PROMPT.md` as the main instruction.
3. Tell Codex to follow `AGENTS.md` and run the loop until final acceptance.
4. Keep `docs/requirements.md` and `docs/guardrails.md` as the source of truth.

Suggested first Codex message:

```md
Follow ORCHESTRATOR_PROMPT.md and AGENTS.md. Read docs/requirements.md and docs/guardrails.md. Then run the frontend, backend, and testing loop until the app satisfies all requirements. Update docs/agent-loop-status.md after each implementation batch. Do not mark complete until lint, typecheck, build, unit tests, integration tests, and Playwright tests pass.
```

## Best Repo Placement

Use root-level `AGENTS.md` so Codex can discover it automatically. Keep specialized agent files under `.codex/agents/`. Keep reusable UI/UX instructions under `.codex/skills/`.
