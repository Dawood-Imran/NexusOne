import unittest

from app.actions.audit_service import AuditEvent, AuditService, InMemoryAuditRepository


class AuditServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryAuditRepository()
        self.service = AuditService(repository=self.repository)

    def test_records_safe_metadata_only(self) -> None:
        audit_id = self.service.record_chat_turn(
            AuditEvent(
                conversation_id="c1",
                turn_id="t1",
                user_id="u001",
                role="employee",
                route="rag",
                category="public_internal",
                tools_called=("retrieve_rag_context",),
                final_answer_status="answered",
                latency_ms=25,
                model_used="deterministic",
                retrieved_doc_ids=("kb-aws-access",),
                allowed_doc_ids=("kb-aws-access",),
            )
        )

        self.assertEqual(1, audit_id)
        row = self.repository.rows[0]
        self.assertEqual("[redacted]", row["query"])
        self.assertEqual(["retrieve_rag_context"], row["tools_called"])
        self.assertEqual(["kb-aws-access"], row["retrieved_doc_ids"])
        self.assertNotIn("Create an IT access ticket", str(row))

    def test_normalizes_status_for_database_constraint(self) -> None:
        self.service.record_chat_turn(
            AuditEvent(
                conversation_id="c1",
                turn_id="t1",
                user_id="u001",
                role="employee",
                route="ticket_create",
                category="own_ticket",
                tools_called=("create_ticket",),
                final_answer_status="ticket_created",
            )
        )

        self.assertEqual("answered", self.repository.rows[0]["final_answer_status"])


if __name__ == "__main__":
    unittest.main()
