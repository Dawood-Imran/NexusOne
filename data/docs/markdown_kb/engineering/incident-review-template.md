---
doc_id: kb-incident-review-template
title: Incident Review Template
source_type: markdown
source_path: data/docs/markdown_kb/engineering/incident-review-template.md
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

# Incident Review Template

## Summary

Incident reviews are blameless and focused on improving systems. They should include enough detail for future retrieval without exposing credentials, private customer data, or restricted financial facts.

## Required Sections

1. Incident ID and severity.
2. Services affected.
3. Customer or internal impact.
4. Detection source.
5. Timeline in local time and UTC.
6. Root cause and contributing factors.
7. Corrective actions with owners and due dates.

## Writing Rules

Use factual language. Avoid naming individual mistakes as root cause. Include logs only after removing secrets, customer identifiers, and restricted revenue details.

## Follow-Up

Managers review corrective actions weekly until closed. Security-related actions also require IT security validation.

## Related Sources

- `kb-on-call-process`
- `kb-service-ownership`
