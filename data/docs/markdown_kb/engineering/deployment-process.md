---
doc_id: kb-deployment-process
title: Deployment Process
source_type: markdown
source_path: data/docs/markdown_kb/engineering/deployment-process.md
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

# Deployment Process

## Summary

Engineering deployments use pull request review, automated checks, staging validation, and controlled production rollout. Production changes must be traceable to Jira and GitHub.

## Standard Flow

1. Merge approved pull request after tests pass.
2. Deploy to staging through the release pipeline.
3. Validate smoke tests and service dashboards.
4. Request production deployment in the release channel.
5. Monitor metrics for at least 30 minutes after release.

## Required Metadata

Each deployment should reference Jira issue, GitHub pull request, service owner, risk level, rollout plan, and rollback command.

## Freeze Windows

Avoid non-urgent production deployments during payroll cutoff, major customer renewals, and announced finance close windows.

## Related Sources

- `kb-aws-access`
- `kb-on-call-process`
- `kb-incident-review-template`
