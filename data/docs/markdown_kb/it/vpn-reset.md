---
doc_id: kb-vpn-reset
title: VPN Reset
source_type: markdown
source_path: data/docs/markdown_kb/it/vpn-reset.md
department: it
permission_profile: it_standard_access
confidentiality: public_internal
allowed_roles: [employee, manager, hr, finance, it_admin, admin_ops, executive, ceo]
allowed_groups: [all_employees, it_team]
allowed_users: []
updated_at: 2026-01-21
canonical: true
generated: true
---

# VPN Reset

## Summary

VPN access is available to employees who need internal systems while away from an office network. Most reset issues are caused by expired SSO sessions, missing MFA approval, or an outdated VPN profile.

## Self-Service Reset

1. Confirm internet access outside the VPN.
2. Sign out of the VPN client.
3. Open SSO in a browser and complete MFA.
4. Download the latest company VPN profile.
5. Reconnect and wait for the device compliance check to finish.

## When To Create A Ticket

Create an IT ticket if the VPN client reports device non-compliance, repeated MFA failure, profile mismatch, or connection timeout longer than five minutes.

## Ticket Details

Include operating system, device asset tag, office or remote location, screenshot of the error, and whether the issue blocks customer or production work.

## Related Sources

- `kb-security-mfa-setup`
- `kb-security-agent-install`
