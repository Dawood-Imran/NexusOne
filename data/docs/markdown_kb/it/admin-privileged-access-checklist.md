---
doc_id: kb-admin-privileged-access-checklist
title: Admin Privileged Access Checklist
source_type: markdown
source_path: data/docs/markdown_kb/it/admin-privileged-access-checklist.md
department: it
permission_profile: it_private
confidentiality: it_sensitive
allowed_roles: [it_admin, ceo]
allowed_groups: [it_team]
allowed_users: []
updated_at: 2026-02-03
canonical: true
generated: true
---

# Admin Privileged Access Checklist

## Access Notice

This document is restricted to IT administrators and the CEO. It contains fictional privileged-access procedures for testing permission-aware retrieval.

## Checklist

1. Confirm requester identity through SSO profile and manager record.
2. Confirm business reason, system owner approval, and time limit.
3. Use a named admin account, never a shared account.
4. Require MFA re-authentication before privilege elevation.
5. Record ticket ID, approver, start time, end time, and commands or console actions performed.
6. Remove access at the approved end time and attach evidence to the ticket.

## Break-Glass Use

Break-glass access is allowed only during active incident response. The incident commander must approve the request, and IT must review logs within one working day.

## Prohibited Actions

Do not export customer data, rotate production secrets without incident approval, or grant persistent admin access through emergency roles.

## Related Sources

- `admin-access-recovery-guide-2026`
- `privileged-access-process-2026`
- `kb-aws-access`
