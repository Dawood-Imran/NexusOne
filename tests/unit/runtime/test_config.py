import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.runtime.config import RuntimeConfig, load_dotenv


class RuntimeConfigTest(unittest.TestCase):
    def test_dotenv_loads_repository_contract_without_overriding_shell_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=fixture-key-do-not-log",
                        "DATABASE_URL=postgresql+psycopg2://fixture:password@localhost/db",
                        "OPENAI_SQL_MODEL=fixture-sql-model",
                        "OPENAI_SQL_TEMPERATURE=0.2",
                        "OPENAI_ANSWER_MODEL=fixture-answer-model",
                        "OPENAI_ANSWER_TEMPERATURE=0.4",
                        "OPENAI_INTENT_MODEL=fixture-intent-model",
                        "OPENAI_INTENT_TEMPERATURE=0.1",
                        "LANGSMITH_TRACING=true",
                        "LANGSMITH_API_KEY=fixture-trace-key",
                        "LANGSMITH_PROJECT=fixture-project",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OPENAI_ANSWER_MODEL": "shell-answer-model"}, clear=True):
                loaded = load_dotenv(dotenv)
                config = RuntimeConfig.from_env()

            self.assertIn("OPENAI_API_KEY", loaded)
            self.assertEqual("shell-answer-model", config.openai_answer_model)
            self.assertEqual("fixture-sql-model", config.openai_sql_model)
            self.assertEqual(0.2, config.openai_sql_temperature)
            self.assertEqual(0.4, config.openai_answer_temperature)
            self.assertEqual("fixture-intent-model", config.openai_intent_model)
            self.assertEqual(0.1, config.openai_intent_temperature)
            self.assertTrue(config.openai_api_key_configured)
            self.assertTrue(config.langsmith_tracing)
            self.assertTrue(config.langsmith_api_key_configured)
            safe = repr(config.safe_metadata())
            self.assertNotIn("fixture-key-do-not-log", safe)
            self.assertNotIn("fixture:password", safe)
            self.assertNotIn("fixture-trace-key", safe)

    def test_placeholder_credentials_are_deterministic_mode(self) -> None:
        config = RuntimeConfig.from_env(
            {
                "OPENAI_API_KEY": "sk-your-key-here",
                "LANGSMITH_API_KEY": "lsv2-your-key-here",
            }
        )

        self.assertFalse(config.openai_api_key_configured)
        self.assertFalse(config.langsmith_api_key_configured)

    def test_missing_values_have_safe_defaults(self) -> None:
        config = RuntimeConfig.from_env({})

        self.assertIsNone(config.database_url)
        self.assertFalse(config.openai_api_key_configured)
        self.assertEqual("gpt-4.1-mini", config.openai_sql_model)
        self.assertEqual("gpt-4.1-mini", config.openai_answer_model)
        self.assertEqual("gpt-4.1-mini", config.openai_intent_model)
        self.assertEqual(0.0, config.openai_intent_temperature)
        self.assertFalse(config.langsmith_tracing)


if __name__ == "__main__":
    unittest.main()
