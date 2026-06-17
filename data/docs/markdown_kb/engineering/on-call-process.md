---
doc_id: kb-on-call-process
title: On-Call Process
source_type: markdown
source_path: data/docs/markdown_kb/engineering/on-call-process.md
department: engineering
permission_profile: public_engineering
confidentiality: department_internal
allowed_roles: [employee, manager, it_admin, executive, ceo]
allowed_groups: [engineering, managers, it_team, executive_team]
allowed_users: []
updated_at: 2026-02-04
canonical: true
generated: true
---

# On-Call Process

## Summary

Engineering teams maintain rotating on-call coverage for production services. The on-call engineer triages alerts, coordinates incident response, and escalates to service owners when needed.

## Responsibilities

- Acknowledge alerts within 10 minutes during assigned coverage.
- Check dashboards, recent deployments, and dependency status.
- Open an incident channel for customer-impacting issues.
- Escalate to service owner or manager when impact is unclear.
- Write a handover note at the end of the shift.

## Escalation

Severity 1 incidents require service owner, engineering manager, and incident commander. Severity 2 incidents require service owner and on-call backup. Security-impacting issues require IT security involvement.

## After Incident

Create an incident review within two working days. Include timeline, impact, detection, root cause, corrective actions, and owner for each action.

## Related Sources

- `kb-incident-review-template`
- `kb-service-ownership`
