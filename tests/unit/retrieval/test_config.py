import unittest

from app.retrieval.config import SOURCE_SIMILARITY_THRESHOLD, HybridRetrievalConfig


class HybridRetrievalConfigTest(unittest.TestCase):
    def test_defaults_are_safe_and_documented(self) -> None:
        config = HybridRetrievalConfig()

        self.assertEqual(0.55, config.lexical_weight)
        self.assertEqual(0.45, config.semantic_weight)
        self.assertEqual(32, config.lexical_candidate_count)
        self.assertEqual(32, config.semantic_candidate_count)
        self.assertEqual(20, config.max_results)
        self.assertEqual(SOURCE_SIMILARITY_THRESHOLD, config.source_similarity_threshold)
        self.assertEqual("0-100", config.safe_metadata()["score_scale"])
        self.assertEqual(
            "100 * weighted(normalized_lexical_max, positive_cosine)",
            config.safe_metadata()["score_normalization"],
        )

    def test_environment_values_are_parsed(self) -> None:
        config = HybridRetrievalConfig.from_env(
            {
                "NEXUSONE_RETRIEVAL_LEXICAL_WEIGHT": "0.7",
                "NEXUSONE_RETRIEVAL_SEMANTIC_WEIGHT": "0.3",
                "NEXUSONE_RETRIEVAL_LEXICAL_CANDIDATES": "9",
                "NEXUSONE_RETRIEVAL_SEMANTIC_CANDIDATES": "11",
                "NEXUSONE_RETRIEVAL_MAX_RESULTS": "5",
                "NEXUSONE_RETRIEVAL_SOURCE_SIMILARITY_THRESHOLD": "50.01",
            }
        )

        self.assertEqual(0.7, config.lexical_weight)
        self.assertEqual(0.3, config.semantic_weight)
        self.assertEqual(9, config.lexical_candidate_count)
        self.assertEqual(11, config.semantic_candidate_count)
        self.assertEqual(5, config.max_results)
        self.assertEqual(50.01, config.source_similarity_threshold)

    def test_invalid_values_fail_validation(self) -> None:
        invalid = (
            {"NEXUSONE_RETRIEVAL_LEXICAL_WEIGHT": "-1"},
            {"NEXUSONE_RETRIEVAL_LEXICAL_WEIGHT": "nan"},
            {"NEXUSONE_RETRIEVAL_LEXICAL_WEIGHT": "0", "NEXUSONE_RETRIEVAL_SEMANTIC_WEIGHT": "0"},
            {"NEXUSONE_RETRIEVAL_LEXICAL_CANDIDATES": "0"},
            {"NEXUSONE_RETRIEVAL_MAX_RESULTS": "not-an-int"},
            {"NEXUSONE_RETRIEVAL_SOURCE_SIMILARITY_THRESHOLD": "100.01"},
        )

        for environment in invalid:
            with self.subTest(environment=environment):
                with self.assertRaises(ValueError):
                    HybridRetrievalConfig.from_env(environment)


if __name__ == "__main__":
    unittest.main()
