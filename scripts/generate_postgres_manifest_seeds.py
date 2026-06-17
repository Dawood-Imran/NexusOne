#!/usr/bin/env python3
"""Generate PostgreSQL seed SQL from NexusOne manifests."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PERMISSIONS = ROOT / "data/generated/manifests/permissions.yaml"
DOCUMENTS = ROOT / "data/generated/manifests/documents.yaml"
CSV_SOURCES = ROOT / "data/generated/manifests/csv_sources.yaml"
INIT_DIR = ROOT / "data/postgres/init"


def parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return [value]


def sql(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    return "'" + str(value).replace("'", "''") + "'"


def sql_array(values: list[str]) -> str:
    if not values:
        return "'{}'::text[]"
    return "ARRAY[" + ", ".join(sql(value) for value in values) + "]::text[]"


def parse_permission_profiles() -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    in_profiles = False
    current_name: str | None = None
    current_field: str | None = None

    for raw_line in PERMISSIONS.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line == "permission_profiles:":
            in_profiles = True
            continue
        if line == "tool_permissions:":
            break
        if not in_profiles:
            continue

        profile = re.match(r"^  ([a-z0-9_]+):$", line)
        if profile:
            current_name = profile.group(1)
            profiles[current_name] = {
                "confidentiality": "",
                "allowed_roles": [],
                "allowed_groups": [],
                "allowed_users": [],
            }
            current_field = None
            continue

        if not current_name:
            continue

        scalar = re.match(r"^    ([a-z_]+): (.+)$", line)
        if scalar:
            key = scalar.group(1)
            value = scalar.group(2).strip()
            current_field = None
            if key == "confidentiality":
                profiles[current_name][key] = value
            elif key in {"allowed_roles", "allowed_groups", "allowed_users"}:
                profiles[current_name][key] = parse_inline_list(value)
                current_field = key if value != "[]" else None
            continue

        list_start = re.match(r"^    (allowed_roles|allowed_groups|allowed_users):$", line)
        if list_start:
            current_field = list_start.group(1)
            profiles[current_name][current_field] = []
            continue

        item = re.match(r"^      - (.+)$", line)
        if item and current_field:
            profiles[current_name][current_field].append(item.group(1).strip())

    return profiles


def parse_document_manifest() -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in DOCUMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        start = re.match(r"^  - doc_id: (.+)$", line)
        if start:
            if current:
                documents.append(current)
            current = {"doc_id": start.group(1).strip()}
            continue
        if not current:
            continue
        field = re.match(r"^    ([a-z_]+): (.+)$", line)
        if not field:
            continue
        key = field.group(1)
        value = field.group(2).strip()
        if key == "key_topics":
            current[key] = parse_inline_list(value)
        else:
            current[key] = value

    if current:
        documents.append(current)

    return documents


def parse_csv_manifest() -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in CSV_SOURCES.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        start = re.match(r"^  - source_id: (.+)$", line)
        if start:
            if current:
                sources.append(current)
            current = {
                "source_id": start.group(1).strip(),
                "source_type": "csv",
                "key_topics": [],
            }
            continue
        if not current:
            continue
        field = re.match(r"^    ([a-z_]+): (.+)$", line)
        if not field:
            continue
        key = field.group(1)
        value = field.group(2).strip()
        if key in {
            "title",
            "source_path",
            "target_table",
            "department",
            "permission_profile",
            "updated_at",
        }:
            current[key] = value

    if current:
        sources.append(current)

    return sources


def write_permission_profile_seed(profiles: dict[str, dict[str, object]]) -> None:
    lines = [
        "-- Generated by scripts/generate_postgres_manifest_seeds.py.",
        "-- Seeds permission profiles before CSV and document metadata loading.",
        "",
        "BEGIN;",
        "",
    ]

    for name, profile in profiles.items():
        description = f"{name} grants for {profile['confidentiality']} content"
        lines.append(
            "INSERT INTO permission_profiles (profile_name, confidentiality, description) "
            f"VALUES ({sql(name)}, {sql(profile['confidentiality'])}, {sql(description)}) "
            "ON CONFLICT (profile_name) DO UPDATE SET "
            "confidentiality = EXCLUDED.confidentiality, "
            "description = EXCLUDED.description;"
        )

    lines.append("")

    for name, profile in profiles.items():
        for role in profile["allowed_roles"]:
            lines.append(
                "INSERT INTO permission_profile_grants (profile_name, grant_type, grant_value) "
                f"VALUES ({sql(name)}, 'role', {sql(role)}) "
                "ON CONFLICT (profile_name, grant_type, grant_value) DO NOTHING;"
            )
        for group in profile["allowed_groups"]:
            lines.append(
                "INSERT INTO permission_profile_grants (profile_name, grant_type, grant_value) "
                f"VALUES ({sql(name)}, 'group', {sql(group)}) "
                "ON CONFLICT (profile_name, grant_type, grant_value) DO NOTHING;"
            )
        for user_id in profile["allowed_users"]:
            lines.append(
                "INSERT INTO permission_profile_grants (profile_name, grant_type, grant_value) "
                f"VALUES ({sql(name)}, 'user', {sql(user_id)}) "
                "ON CONFLICT (profile_name, grant_type, grant_value) DO NOTHING;"
            )

    lines.extend(["", "COMMIT;", ""])
    (INIT_DIR / "002_seed_permission_profiles.sql").write_text("\n".join(lines), encoding="utf-8")


def normalize_doc_from_csv(source: dict[str, object]) -> dict[str, object]:
    return {
        "doc_id": source["source_id"],
        "title": source["title"],
        "source_type": "csv",
        "source_path": source["source_path"],
        "department": source["department"],
        "permission_profile": source["permission_profile"],
        "updated_at": source["updated_at"],
        "key_topics": [str(source.get("target_table", ""))],
    }


def write_document_seed(
    documents: list[dict[str, object]],
    csv_sources: list[dict[str, object]],
    profiles: dict[str, dict[str, object]],
) -> None:
    seed_docs = documents + [normalize_doc_from_csv(source) for source in csv_sources]
    lines = [
        "-- Generated by scripts/generate_postgres_manifest_seeds.py.",
        "-- Seeds document metadata and document permission grants from manifests.",
        "",
        "BEGIN;",
        "",
    ]

    for doc in seed_docs:
        profile_name = str(doc["permission_profile"])
        profile = profiles[profile_name]
        key_topics = doc.get("key_topics", [])
        if not isinstance(key_topics, list):
            key_topics = []
        lines.append(
            "INSERT INTO documents ("
            "doc_id, title, source_type, source_path, department, permission_profile, "
            "confidentiality, created_at, updated_at, canonical, generated, status, key_topics"
            ") VALUES ("
            f"{sql(doc['doc_id'])}, {sql(doc['title'])}, {sql(doc['source_type'])}, "
            f"{sql(doc['source_path'])}, {sql(doc['department'])}, {sql(profile_name)}, "
            f"{sql(profile['confidentiality'])}, {sql(doc['updated_at'])}, {sql(doc['updated_at'])}, "
            f"true, true, 'active', {sql_array([str(topic) for topic in key_topics])}"
            ") ON CONFLICT (doc_id) DO UPDATE SET "
            "title = EXCLUDED.title, "
            "source_type = EXCLUDED.source_type, "
            "source_path = EXCLUDED.source_path, "
            "department = EXCLUDED.department, "
            "permission_profile = EXCLUDED.permission_profile, "
            "confidentiality = EXCLUDED.confidentiality, "
            "updated_at = EXCLUDED.updated_at, "
            "canonical = EXCLUDED.canonical, "
            "generated = EXCLUDED.generated, "
            "status = EXCLUDED.status, "
            "key_topics = EXCLUDED.key_topics;"
        )

    lines.append("")

    for doc in seed_docs:
        profile = profiles[str(doc["permission_profile"])]
        for role in profile["allowed_roles"]:
            lines.append(
                "INSERT INTO document_permissions (doc_id, allowed_role) "
                f"VALUES ({sql(doc['doc_id'])}, {sql(role)}) "
                "ON CONFLICT (doc_id, allowed_role) DO NOTHING;"
            )
        for group in profile["allowed_groups"]:
            lines.append(
                "INSERT INTO document_permissions (doc_id, allowed_group) "
                f"VALUES ({sql(doc['doc_id'])}, {sql(group)}) "
                "ON CONFLICT (doc_id, allowed_group) DO NOTHING;"
            )
        for user_id in profile["allowed_users"]:
            lines.append(
                "INSERT INTO document_permissions (doc_id, allowed_user_id) "
                f"VALUES ({sql(doc['doc_id'])}, {sql(user_id)}) "
                "ON CONFLICT (doc_id, allowed_user_id) DO NOTHING;"
            )

    lines.extend(["", "COMMIT;", ""])
    (INIT_DIR / "004_seed_documents_and_permissions.sql").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    profiles = parse_permission_profiles()
    documents = parse_document_manifest()
    csv_sources = parse_csv_manifest()

    write_permission_profile_seed(profiles)
    write_document_seed(documents, csv_sources, profiles)

    print(f"Generated {len(profiles)} permission profiles")
    print(f"Generated metadata for {len(documents)} document-manifest sources")
    print(f"Generated metadata for {len(csv_sources)} CSV sources")


if __name__ == "__main__":
    main()
