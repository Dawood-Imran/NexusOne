---
doc_id: kb-aws-access
title: AWS Access Request
source_type: markdown
source_path: data/docs/markdown_kb/it/aws-access.md
department: it
permission_profile: public_engineering
confidentiality: department_internal
allowed_roles: [employee, manager, it_admin, executive, ceo]
allowed_groups: [engineering, managers, it_team, executive_team]
allowed_users: []
updated_at: 2026-02-02
canonical: true
generated: true
---

# AWS Access Request

## Summary

AWS access is limited to engineering, approved managers, IT administrators, executives, and the CEO. Requests must be scoped to a specific account, environment, role, and duration.

## Request Steps

1. Create an IT access ticket with category `Cloud access`.
2. Select the target account: sandbox, staging, production-readonly, or production-breakglass.
3. Add business reason, Jira link, service owner, and manager approval.
4. For production access, include planned start and end time.
5. Wait for IT to assign the least-privilege SSO group.

## Approval Matrix

Sandbox and staging access require manager approval. Production-readonly requires manager and service owner approval. Production-breakglass requires IT admin approval and incident reference.

## User Guidance

Do not share AWS console sessions, credentials, screenshots containing account identifiers, or exported data. If access is no longer needed, ask IT to remove it.

## Related Sources

- `kb-github-access`
- `kb-deployment-process`
- `kb-admin-privileged-access-checklist`
