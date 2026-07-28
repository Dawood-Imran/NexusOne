"""Explicit server-sent event framing for the chat streaming contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


STREAM_CONTENT_TYPE = "text/event-stream; charset=utf-8"
STREAM_EVENT_TYPES = frozenset(
    {
        "response.start",
        "response.delta",
        "response.error",
        "response.complete",
    }
)


def encode_sse_event(event_type: str, payload: Mapping[str, Any]) -> bytes:
    """Encode one allowlisted, JSON-backed SSE event.

    The event name and JSON ``type`` are both present intentionally.  This
    makes the wire format easy to inspect with generic SSE tooling while also
    giving fetch-based clients a self-describing payload.
    """

    if event_type not in STREAM_EVENT_TYPES:
        raise ValueError("unsupported stream event type")
    data = {"type": event_type, **dict(payload)}
    data["type"] = event_type
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event_type}\ndata: {serialized}\n\n".encode("utf-8")


def is_stream_event(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("type") in STREAM_EVENT_TYPES
