"""Server-side access policy for chat requests."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.auth.profiles import UserProfile


ROLE_ALLOWED_CATEGORIES: dict[str, set[str]] = {
    "employee": {"public_internal", "own_ticket"},
    "manager": {"public_internal", "own_ticket", "manager_only", "admin_private"},
    "hr": {"public_internal", "own_ticket", "manager_only", "hr_sensitive"},
    "finance": {"public_internal", "own_ticket", "finance_sensitive"},
    "it_admin": {"public_internal", "own_ticket", "it_sensitive"},
    "admin_ops": {"public_internal", "own_ticket", "admin_private"},
    "executive": {"public_internal", "own_ticket", "manager_only", "finance_sensitive", "executive"},
    "ceo": {
        "public_internal",
        "own_ticket",
        "manager_only",
        "hr_sensitive",
        "finance_sensitive",
        "it_sensitive",
        "admin_private",
        "executive",
        "ceo_only",
    },
}

SAFE_ALTERNATIVES = [
    "public company policies",
    "your own support tickets",
    "general process guidance",
]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    category: str
    reason_code: str
    message: str
    allowed_alternatives: tuple[str, ...] = tuple(SAFE_ALTERNATIVES)

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "category": self.category,
            "reason_code": self.reason_code,
            "message": self.message,
            "allowed_alternatives": list(self.allowed_alternatives),
        }


def classify_data_category(message: str) -> str:
    lowered = message.lower()
    if _looks_like_prompt_injection(lowered):
        return "prompt_injection"
    if re.search(r"\b(ceo|employee|staff|all employees?)\b.*\b(salary|salaries|compensation|payroll data)\b", lowered):
        return "hr_sensitive"
    if any(term in lowered for term in ("acquisition notes", "m&a", "ceo-only", "ceo private")):
        return "ceo_only"
    if any(term in lowered for term in ("board meeting", "strategy memo", "company strategy", "executive document")):
        return "executive"
    if any(term in lowered for term in ("q4 revenue risk", "revenue risks", "revenue risk register", "revenue at risk")):
        return "executive"
    if any(term in lowered for term in ("department budget", "budget utilization", "vendor payment", "finance summary")):
        return "finance_sensitive"
    if any(term in lowered for term in ("hr escalation", "employee relations", "benefits vendor", "payroll issue queue")):
        return "hr_sensitive"
    if any(term in lowered for term in ("privileged access", "security incident", "admin access recovery")):
        return "it_sensitive"
    if any(term in lowered for term in ("facilities queue", "admin ticket queue")):
        return "admin_private"
    if any(term in lowered for term in ("hiring request", "performance improvement", "team onboarding")):
        return "manager_only"
    if "ticket" in lowered or "case" in lowered:
        return "own_ticket"
    return "public_internal"


def check_message_access(profile: UserProfile, message: str) -> AccessDecision:
    category = classify_data_category(message)
    if category == "prompt_injection":
        return AccessDecision(
            allowed=False,
            category=category,
            reason_code="PROMPT_INJECTION",
            message="I cannot follow instructions that try to bypass role rules or reveal hidden system information.",
        )

    allowed_categories = ROLE_ALLOWED_CATEGORIES.get(profile.role, set())
    if category in allowed_categories:
        return AccessDecision(
            allowed=True,
            category=category,
            reason_code="ALLOWED",
            message="Allowed by role policy.",
        )
    return AccessDecision(
        allowed=False,
        category=category,
        reason_code="ROLE_NOT_AUTHORIZED",
        message=(
            "I cannot access that information for your role. "
            "You can ask about public company policies, your own tickets, or general process guidance instead."
        ),
    )


def _looks_like_prompt_injection(lowered_message: str) -> bool:
    unsafe_patterns = (
        "ignore previous instructions",
        "ignore all instructions",
        "bypass",
        "jailbreak",
        "developer message",
        "system prompt",
        "hidden prompt",
        "reveal your instructions",
        "act as ceo",
        "pretend to be ceo",
        "show me executive documents",
        "dump hidden context",
    )
    return any(pattern in lowered_message for pattern in unsafe_patterns)
