"""Deterministic action routing and field extraction."""

from __future__ import annotations

import re

from app.actions.ticket_service import TicketRequest


TICKET_CREATE_PATTERNS = (
    "create a ticket",
    "create ticket",
    "raise a ticket",
    "open a ticket",
    "open an it ticket",
    "open hr ticket",
    "open admin ticket",
    "i need help with",
    "request access card",
    "payroll issue",
)


def wants_ticket_creation(message: str) -> bool:
    lowered = message.lower()
    if any(pattern in lowered for pattern in TICKET_CREATE_PATTERNS):
        return True
    return bool(re.search(r"\b(create|raise|open)\b.*\b(ticket|case)\b", lowered))


def extract_ticket_request(message: str) -> TicketRequest:
    lowered = message.lower()
    department = _extract_department(lowered)
    category = _extract_category(lowered, department)
    priority = _extract_priority(lowered)
    description = _extract_description(message)
    return TicketRequest(
        department=department,
        category=category,
        priority=priority,
        description=description,
    )


def _extract_department(lowered: str) -> str | None:
    if any(term in lowered for term in (" hr ", "payroll", "benefit", "leave", "onboarding")):
        return "hr"
    if any(term in lowered for term in ("admin", "access card", "seating", "visitor", "facilities", "office")):
        return "admin"
    if any(term in lowered for term in (" it ", "laptop", "vpn", "mfa", "aws", "github", "software", "cloud")):
        return "it"
    if lowered.startswith("it ") or lowered.endswith(" it"):
        return "it"
    if lowered.startswith("hr ") or lowered.endswith(" hr"):
        return "hr"
    return None


def _extract_category(lowered: str, department: str | None) -> str | None:
    category_terms = (
        ("aws", "cloud_access"),
        ("cloud", "cloud_access"),
        ("github", "software_access"),
        ("software", "software_access"),
        ("laptop", "laptop_issue"),
        ("vpn", "vpn"),
        ("mfa", "mfa"),
        ("payroll", "payroll_question"),
        ("benefit", "benefits"),
        ("leave", "leave_support"),
        ("onboarding", "onboarding"),
        ("access card", "access_card"),
        ("seating", "seating"),
        ("visitor", "visitor"),
        ("facilities", "facilities"),
    )
    for term, category in category_terms:
        if term in lowered:
            return category
    if department and "ticket" not in lowered:
        return f"{department}_support"
    return None


def _extract_priority(lowered: str) -> str:
    for priority in ("urgent", "high", "low"):
        if priority in lowered:
            return priority
    return "normal"


def _extract_description(message: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", message.strip())
    cleaned = re.sub(r"^(please\s+)?(create|raise|open)\s+(an?\s+)?(\w+\s+)?(ticket|case)\s*(for|about|because|:)?\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned or None
