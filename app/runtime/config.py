"""Safe, predictable runtime configuration for NexusOne entry points.

The project intentionally avoids a hard dependency on python-dotenv.  The small
loader below implements the repository's ``.env`` contract while preserving
explicit shell values and never printing or returning secret values.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_PLACEHOLDER_VALUES = {
    "sk-your-key-here",
    "lsv2-your-key-here",
    "your-key-here",
    "changeme",
}


def repository_root() -> Path:
    """Return the repository root independent of the process working directory."""

    return Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | str | None = None, *, override: bool = False) -> tuple[str, ...]:
    """Load simple ``KEY=VALUE`` entries without exposing their values.

    ``.env`` is loaded only when an entry is not already in ``os.environ`` by
    default.  This makes shell/container configuration authoritative and lets
    the web app launched from any working directory consistently find the
    repository root file.  The returned tuple contains names only, which is
    suitable for safe diagnostics and tests.
    """

    dotenv_path = Path(path) if path is not None else repository_root() / ".env"
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return ()

    loaded: list[str] = []
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        loaded.append(key)
    return tuple(loaded)


@dataclass(frozen=True)
class RuntimeConfig:
    """Non-secret runtime settings used by the HTTP service and graph."""

    database_url: str | None
    openai_api_key_configured: bool
    openai_sql_model: str
    openai_sql_temperature: float
    openai_answer_model: str
    openai_answer_temperature: float
    langsmith_tracing: bool
    langsmith_api_key_configured: bool
    langsmith_project: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "RuntimeConfig":
        values = os.environ if environ is None else environ
        return cls(
            database_url=_optional_value(values.get("DATABASE_URL")),
            openai_api_key_configured=_configured_secret(values.get("OPENAI_API_KEY")),
            openai_sql_model=values.get("OPENAI_SQL_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            openai_sql_temperature=_temperature(values.get("OPENAI_SQL_TEMPERATURE"), default=0.0),
            openai_answer_model=values.get("OPENAI_ANSWER_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            openai_answer_temperature=_temperature(values.get("OPENAI_ANSWER_TEMPERATURE"), default=0.0),
            langsmith_tracing=_as_bool(values.get("LANGSMITH_TRACING", values.get("LANGCHAIN_TRACING_V2", "false"))),
            langsmith_api_key_configured=_configured_secret(values.get("LANGSMITH_API_KEY")),
            langsmith_project=values.get("LANGSMITH_PROJECT", "nexusone-copilot").strip() or "nexusone-copilot",
        )

    def safe_metadata(self) -> dict[str, object]:
        """Return capability metadata with no URL, key, prompt, or context."""

        return {
            "database_configured": self.database_url is not None,
            "openai_api_key_configured": self.openai_api_key_configured,
            "openai_sql_model": self.openai_sql_model,
            "openai_sql_temperature": self.openai_sql_temperature,
            "openai_answer_model": self.openai_answer_model,
            "openai_answer_temperature": self.openai_answer_temperature,
            "langsmith_tracing": self.langsmith_tracing,
            "langsmith_api_key_configured": self.langsmith_api_key_configured,
            "langsmith_project": self.langsmith_project,
        }


def _optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _configured_secret(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return bool(normalized) and normalized not in _PLACEHOLDER_VALUES


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _temperature(value: str | None, *, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return max(0.0, min(2.0, parsed))


def _parse_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None
    key, raw_value = line.split("=", 1)
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return None
    return key, _parse_value(raw_value.strip())


def _parse_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    # Treat an unquoted '#' preceded by whitespace as an inline comment.
    for index, character in enumerate(value):
        if character == "#" and index > 0 and value[index - 1].isspace():
            return value[:index].rstrip()
    return value
