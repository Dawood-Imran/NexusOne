---
doc_id: kb-security-mfa-setup
title: Security MFA Setup
source_type: markdown
source_path: data/docs/markdown_kb/public/security-mfa-setup.md
department: it
permission_profile: public_internal
confidentiality: public_internal
allowed_roles: [employee, manager, hr, finance, it_admin, admin_ops, executive, ceo]
allowed_groups: [all_employees]
allowed_users: []
updated_at: 2026-01-25
canonical: true
generated: true
---

# Security MFA Setup

## Summary

MFA is required for SSO, HRIS, Finance Portal, GitHub, AWS, and VPN. Employees should use the approved authenticator app or a registered hardware key.

## Setup Steps

1. Open the SSO enrollment link from the onboarding email.
2. Scan the QR code with the approved authenticator app.
3. Save recovery codes in the approved password manager.
4. Register a backup factor when available.
5. Confirm SSO login from a company-managed device.

## Reset Rules

Employees who lose MFA access must create an IT ticket from a verified company email. IT will validate identity through manager confirmation or HRIS profile checks before resetting MFA.

## Security Notes

Never approve an MFA prompt you did not initiate. Report suspicious MFA prompts in Slack `#security-help` and create an IT security ticket.

## Related Sources

- `kb-vpn-reset`
- `kb-company-tools`
