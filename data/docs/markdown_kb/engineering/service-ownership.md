---
doc_id: kb-service-ownership
title: Service Ownership
source_type: markdown
source_path: data/docs/markdown_kb/engineering/service-ownership.md
department: engineering
permission_profile: public_engineering
confidentiality: department_internal
allowed_roles: [employee, manager, it_admin, executive, ceo]
allowed_groups: [engineering, managers, it_team, executive_team]
allowed_users: []
updated_at: 2026-01-29
canonical: true
generated: true
---

# Service Ownership

## Summary

Every production service must have an owning team, primary service owner, backup owner, on-call rotation, runbook, and escalation channel.

## Ownership Fields

| Field | Description |
|---|---|
| Owning team | Team accountable for reliability and roadmap |
| Service owner | Primary decision owner for incidents and changes |
| Backup owner | Secondary escalation contact |
| Runbook | Operational guide for alerts and maintenance |
| Data classification | Public internal, customer, finance, HR, or security impact |

## Change Rule

Ownership changes require manager approval and must be updated in the service catalog before the next deployment.

## Escalation

If ownership is unclear during an incident, the on-call engineer escalates to the engineering manager and incident commander.

## Related Sources

- `kb-deployment-process`
- `kb-on-call-process`
