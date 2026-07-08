from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_JS = ROOT / "frontend" / "static" / "app.js"
INDEX_HTML = ROOT / "frontend" / "static" / "index.html"


class StaticChatUIContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app_js = APP_JS.read_text(encoding="utf-8")
        self.index_html = INDEX_HTML.read_text(encoding="utf-8")

    def test_combined_responses_render_citations_and_sql_sources(self) -> None:
        self.assertIn("function collectSourceItems(payload)", self.app_js)
        self.assertIn("const citations = Array.isArray(payload.citations) ? payload.citations : [];", self.app_js)
        self.assertIn("const sources = Array.isArray(payload.sources) ? payload.sources : [];", self.app_js)
        self.assertIn("return [...citations, ...sources];", self.app_js)
        self.assertIn("const sourceItems = collectSourceItems(payload);", self.app_js)

    def test_inline_citation_buttons_link_to_source_cards(self) -> None:
        self.assertIn("className = \"citation-ref\"", self.app_js)
        self.assertIn("aria-label", self.app_js)
        self.assertIn("document.querySelector(`#source-${referenceId}`)", self.app_js)
        self.assertIn("source.scrollIntoView", self.app_js)

    def test_source_cards_show_permitted_chunk_text(self) -> None:
        self.assertIn("const sourceText = item.text || item.excerpt;", self.app_js)
        self.assertIn("className = \"source-excerpt\"", self.app_js)
        self.assertIn("excerpt.textContent = sourceText;", self.app_js)

    def test_trace_control_exists_in_chat_shell(self) -> None:
        self.assertIn("id=\"traceToggle\"", self.index_html)
        self.assertIn("Show node trace", self.index_html)


if __name__ == "__main__":
    unittest.main()
