import unittest

from app.actions.feedback_service import FeedbackService, InMemoryFeedbackRepository


class FeedbackServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryFeedbackRepository()
        self.service = FeedbackService(repository=self.repository)

    def test_stores_valid_feedback(self) -> None:
        result = self.service.submit_feedback(
            conversation_id="c1",
            turn_id="t1",
            user_id="u001",
            rating="helpful",
            comment="The source was useful.",
        )

        self.assertEqual("stored", result.status)
        self.assertEqual(1, result.feedback_id)
        self.assertEqual("helpful", self.repository.rows[0]["rating"])
        self.assertEqual("The source was useful.", self.repository.rows[0]["comment"])

    def test_rejects_unknown_rating(self) -> None:
        result = self.service.submit_feedback(
            conversation_id="c1",
            turn_id="t1",
            user_id="u001",
            rating="leaked_salary",
        )

        self.assertEqual("error", result.status)
        self.assertEqual("INVALID_FEEDBACK_RATING", result.reason_code)
        self.assertEqual([], self.repository.rows)

    def test_comment_is_length_limited(self) -> None:
        self.service.submit_feedback(
            conversation_id="c1",
            turn_id="t1",
            user_id="u001",
            rating="not_helpful",
            comment="x" * 1200,
        )

        self.assertEqual(1000, len(self.repository.rows[0]["comment"]))


if __name__ == "__main__":
    unittest.main()
