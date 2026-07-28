"""Shared metadata access checks for retrieval fallbacks."""

from __future__ import annotations

from collections.abc import Sequence

from app.auth.profiles import UserProfile


# These category gates mirror docs/guardrails.md.  Source role/group grants
# still need to match; a broad metadata grant cannot override confidentiality.
_CONFIDENTIALITY_ROLES: dict[str, set[str]] = {
    "manager_only": {"manager", "hr", "executive", "ceo"},
    "hr_sensitive": {"hr", "ceo"},
    "finance_sensitive": {"finance", "executive", "ceo"},
    "it_sensitive": {"it_admin", "ceo"},
    "admin_private": {"manager", "admin_ops", "ceo"},
    "executive": {"executive", "ceo"},
    "ceo_only": {"ceo"},
}
_CONFIDENTIALITY_GROUPS: dict[str, set[str]] = {
    "manager_only": {"managers"},
    "hr_sensitive": {"hr_team"},
    "finance_sensitive": {"finance_team", "finance_viewers"},
    "it_sensitive": {"it_team"},
    "admin_private": {"admin_ops_team", "managers"},
    "executive": {"executive_team"},
    "ceo_only": set(),
}
_KNOWN_CONFIDENTIALITY = {"public_internal", "department_internal", *_CONFIDENTIALITY_ROLES}


def can_access_metadata(
    profile: UserProfile,
    *,
    department: str,
    confidentiality: str,
    allowed_roles: Sequence[str],
    allowed_groups: Sequence[str],
    allowed_users: Sequence[str],
) -> bool:
    """Apply explicit grants plus confidentiality/category gates.

    ``department`` identifies the owning department, not an implicit grant.
    Access still requires an explicit role, group, or user grant. For
    department-scoped content, a role-only grant also requires a matching
    profile department; an explicit group grant is the team-scoped exception.
    Explicit user grants support the guardrail's "explicitly shared users"
    exception for known categories.
    """

    if profile.status != "active" or confidentiality not in _KNOWN_CONFIDENTIALITY:
        return False

    user_grant = profile.user_id in allowed_users
    role_grant = profile.role in allowed_roles
    group_grant = bool(set(profile.groups).intersection(allowed_groups))
    if not (user_grant or role_grant or group_grant):
        return False
    if user_grant:
        return True
    if confidentiality == "department_internal":
        return group_grant or (role_grant and (not department or profile.department == department))
    if confidentiality in _CONFIDENTIALITY_ROLES:
        role_allowed = profile.role in _CONFIDENTIALITY_ROLES[confidentiality]
        group_allowed = bool(set(profile.groups).intersection(_CONFIDENTIALITY_GROUPS[confidentiality]))
        return role_allowed or group_allowed
    return True
