---
doc_id: kb-company-tools
title: Company Tools
source_type: markdown
source_path: data/docs/markdown_kb/public/company-tools.md
department: it
permission_profile: public_internal
confidentiality: public_internal
allowed_roles: [employee, manager, hr, finance, it_admin, admin_ops, executive, ceo]
allowed_groups: [all_employees]
allowed_users: []
updated_at: 2026-02-01
canonical: true
generated: true
---

# Company Tools

## Summary

NexusOne Technologies uses a small set of approved tools for day-to-day work. Employees should use company-managed accounts only and should not move company files to personal services.

## Core Tools

| Tool | Primary use | Access path |
|---|---|---|
| Slack | Team chat, announcements, incident channels | Provisioned during onboarding |
| Jira | Engineering, IT, Admin, HR, and Finance tickets | Provisioned through SSO |
| GitHub | Source code and engineering reviews | Request through IT KB |
| AWS | Cloud consoles and production resources | Engineering access request only |
| HRIS | Leave, payroll profile, performance tasks | Provisioned by HR |
| Finance Portal | Expense claims and reimbursements | Available to all employees |
| Admin Portal | Visitor, desk, and facilities requests | Available to all employees |

## Access Rules

Standard access is granted through SSO after onboarding. GitHub and AWS require extra approval because they can expose source code, customer data, or production infrastructure.

## Common Requests

- For GitHub access, submit an IT access request with repository or organization scope.
- For AWS access, include environment, account, business reason, and manager approval.
- For HRIS issues, create an HR ticket under `Profile or payroll access`.
- For Finance Portal issues, create a Finance ticket under `Expense portal issue`.

## Related Sources

- `kb-github-access`
- `kb-aws-access`
- `kb-security-mfa-setup`
- `kb-expense-claim-how-to`
