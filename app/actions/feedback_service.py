"""Answer feedback capture service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine


ALLOWED_RATINGS = {
    "helpful",
    "not_helpful",
    "incorrect",
    "missing_source",
    "outdated",
    "permission_issue",
}
MAX_COMMENT_CHARS = 1000


@dataclass(frozen=True)
class FeedbackResult:
    status: str
    feedback_id: int | None = None
    message: str = ""
    reason_code: str | None = None


class FeedbackRepository(Protocol):
    def insert_feedback(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        user_id: str | None,
        rating: str,
        comment: str | None,
    ) -> int:
        """Persist feedback and return its id."""


class FeedbackService:
    def __init__(self, repository: FeedbackRepository | None = None) -> None:
        self.repository = repository or InMemoryFeedbackRepository()

    def submit_feedback(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        user_id: str | None,
        rating: str,
        comment: str | None = None,
    ) -> FeedbackResult:
        normalized_rating = rating.strip().lower()
        if normalized_rating not in ALLOWED_RATINGS:
            return FeedbackResult(
                status="error",
                reason_code="INVALID_FEEDBACK_RATING",
                message="Choose one of the supported feedback ratings.",
            )
        normalized_comment = normalize_comment(comment)
        feedback_id = self.repository.insert_feedback(
            conversation_id=conversation_id or "web-chat",
            turn_id=turn_id or "web-turn",
            user_id=user_id or None,
            rating=normalized_rating,
            comment=normalized_comment,
        )
        return FeedbackResult(status="stored", feedback_id=feedback_id, message="Feedback stored.")


class InMemoryFeedbackRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def insert_feedback(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        user_id: str | None,
        rating: str,
        comment: str | None,
    ) -> int:
        feedback_id = len(self.rows) + 1
        self.rows.append(
            {
                "feedback_id": feedback_id,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "user_id": user_id,
                "rating": rating,
                "comment": comment,
                "created_at": datetime.now(UTC).replace(microsecond=0),
            }
        )
        return feedback_id


class SQLAlchemyFeedbackRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def insert_feedback(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        user_id: str | None,
        rating: str,
        comment: str | None,
    ) -> int:
        with self.engine.begin() as connection:
            feedback_id = connection.execute(
                text(
                    """
                    INSERT INTO feedback (conversation_id, turn_id, user_id, rating, comment)
                    VALUES (:conversation_id, :turn_id, :user_id, :rating, :comment)
                    RETURNING feedback_id
                    """
                ),
                {
                    "conversation_id": conversation_id,
                    "turn_id": turn_id,
                    "user_id": user_id,
                    "rating": rating,
                    "comment": comment,
                },
            ).scalar_one()
        return int(feedback_id)


def normalize_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    normalized = " ".join(comment.strip().split())
    return normalized[:MAX_COMMENT_CHARS] or None
