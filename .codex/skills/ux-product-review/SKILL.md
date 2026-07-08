---
name: ux-product-review
description: ux review guidance for role-based ai chatbot web applications. use when evaluating user journeys, playwright browser behavior, onboarding, chat flows, permission-denied experiences, error recovery, information architecture, and whether the product satisfies requirements from a real user's perspective.
---

# UX Product Review Skill

Use this skill when evaluating whether the app works well for real users and satisfies the requirements document.

## Core UX Principle

The user should always understand:

- Where they are.
- What role or permission context applies.
- What they can ask.
- Why something is denied.
- What they can do next.

## Required UX Journeys

Review and test these journeys:

1. First visit or signed-out state.
2. Login or mocked authentication flow.
3. Role-specific landing state.
4. Normal employee asks an allowed question.
5. Normal employee asks a restricted question.
6. CEO or authorized role asks an allowed executive question.
7. User asks an ambiguous sensitive question.
8. User attempts prompt injection or role escalation.
9. Backend or model error occurs.
10. User returns after a failed or denied answer and continues productively.

## Denied Access UX

A denied answer should:

- Be direct and calm.
- Avoid leaking restricted data.
- Avoid confirming confidential records unless allowed.
- Offer safe alternatives.
- Avoid blaming the user.

Good pattern:

> I cannot access that information for your role. You can ask about company policies, public handbook information, or general process guidance instead.

Bad patterns:

- “You are not senior enough to see salary data.”
- “The salary is confidential, but it is stored in the executive database.”
- “Access denied.” with no next step.

## Playwright UX Review Method

When browser access is available:

1. Start the app locally.
2. Navigate through each critical role journey.
3. Inspect actual rendered screens, not just code.
4. Check desktop and mobile viewport behavior.
5. Verify loading, empty, error, denied, and success states.
6. Capture failures with reproduction steps.
7. Convert failures into frontend, backend, or testing tasks.

## UX Completion Criteria

The UX is acceptable only when:

- A first-time user can understand the product quickly.
- The chat workflow is obvious.
- Role restrictions are understandable without leaking sensitive information.
- Errors and denials allow recovery.
- The interface remains usable on mobile.
- Core journeys are verified with Playwright.
- The requirements document has traceable coverage.

## Review Output Format

Use this format when reporting UX findings:

```md
## UX Review

### Blocking Issues
- [Owner] Issue — evidence — required fix

### Important Improvements
- [Owner] Issue — evidence — required fix

### Passed Checks
- Check — evidence

### Required Tests
- Scenario — expected result
```
