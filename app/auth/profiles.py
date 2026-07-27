"""Synthetic NexusOne profiles used by the local server-side auth service."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.sql_subgraph.state import UserContext


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    name: str
    email: str
    role: str
    department: str
    title: str
    location: str
    groups: tuple[str, ...]
    status: str = "active"

    def to_context(self) -> UserContext:
        return UserContext(
            user_id=self.user_id,
            role=self.role,
            department=self.department,
            location=self.location,
            groups=self.groups,
            status=self.status,
        )

    def to_public_dict(self) -> dict[str, object]:
        """Return only the fields safe for the authenticated UI contract.

        Email addresses, group memberships, and account status remain server
        concerns.  Role and profile data are selected from this immutable
        server-owned record, never from a request body.
        """

        return {
            "user_id": self.user_id,
            "name": self.name,
            "title": self.title,
            "role": self.role,
            "department": self.department,
            "location": self.location,
            "avatar": None,
        }


PROFILES: dict[str, UserProfile] = {
    "u001": UserProfile(
        user_id="u001",
        name="Ayesha Khan",
        email="ayesha.khan@nexusone.example",
        role="employee",
        department="engineering",
        title="Software Engineer",
        location="Pakistan",
        groups=("all_employees", "engineering", "pakistan_office"),
    ),
    "u002": UserProfile(
        user_id="u002",
        name="Bilal Ahmed",
        email="bilal.ahmed@nexusone.example",
        role="manager",
        department="engineering",
        title="Engineering Manager",
        location="Pakistan",
        groups=("all_employees", "engineering", "managers", "pakistan_office"),
    ),
    "u003": UserProfile(
        user_id="u003",
        name="Sara Malik",
        email="sara.malik@nexusone.example",
        role="hr",
        department="hr",
        title="HR Specialist",
        location="Pakistan",
        groups=("all_employees", "hr_team", "pakistan_office"),
    ),
    "u004": UserProfile(
        user_id="u004",
        name="Hamza Farooq",
        email="hamza.farooq@nexusone.example",
        role="finance",
        department="finance",
        title="Finance Analyst",
        location="UAE",
        groups=("all_employees", "finance_team", "finance_viewers", "uae_office"),
    ),
    "u005": UserProfile(
        user_id="u005",
        name="Omar Siddiqui",
        email="omar.siddiqui@nexusone.example",
        role="it_admin",
        department="it",
        title="IT Admin",
        location="Pakistan",
        groups=("all_employees", "it_team", "pakistan_office"),
    ),
    "u006": UserProfile(
        user_id="u006",
        name="Fatima Noor",
        email="fatima.noor@nexusone.example",
        role="ceo",
        department="executive",
        title="CEO",
        location="UAE",
        groups=("all_employees", "managers", "executive_team", "finance_viewers", "uae_office"),
    ),
    "u007": UserProfile(
        user_id="u007",
        name="Emma Wilson",
        email="emma.wilson@nexusone.example",
        role="executive",
        department="executive",
        title="Chief Customer Officer",
        location="UK",
        groups=("all_employees", "executive_team", "uk_office"),
    ),
    "u008": UserProfile(
        user_id="u008",
        name="Zain Qureshi",
        email="zain.qureshi@nexusone.example",
        role="admin_ops",
        department="admin",
        title="Admin Operations Lead",
        location="Pakistan",
        groups=("all_employees", "admin_ops_team", "pakistan_office"),
    ),
}


def list_profiles() -> list[dict[str, object]]:
    return [profile.to_public_dict() for profile in PROFILES.values()]


def get_profile(user_id: str) -> UserProfile | None:
    return PROFILES.get(user_id)
