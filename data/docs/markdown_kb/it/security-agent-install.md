---
doc_id: kb-security-agent-install
title: Security Agent Install
source_type: markdown
source_path: data/docs/markdown_kb/it/security-agent-install.md
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

# Security Agent Install

## Summary

The endpoint security agent verifies encryption, patch level, malware protection, and device inventory status. VPN and some SaaS access can be blocked when the agent is missing or unhealthy.

## Install Steps

1. Open the company device management portal.
2. Choose `Install security agent`.
3. Approve the installer from the operating system prompt.
4. Restart the device after installation.
5. Confirm status shows `Healthy` in the portal.

## Common Issues

If installation fails, check free disk space, operating system version, local administrator prompt, and network connectivity. Do not install third-party endpoint tools without IT approval.

## Compliance Rule

Devices without a healthy security agent for more than three working days may lose VPN, GitHub, and AWS access until fixed.

## Related Sources

- `kb-vpn-reset`
- `general-security-guidelines-2026`
