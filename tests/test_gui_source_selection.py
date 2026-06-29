import unittest
from unittest.mock import Mock

import config
from src.gui.main_window import AgentTab, CrawlTab, NlpTab


class GuiSourceSelectionTests(unittest.TestCase):
    def _make_tab(self, selected_source=None):
        tab = AgentTab.__new__(AgentTab)

        class SourceVar:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        tab.source_var = SourceVar(selected_source)
        return tab

    def test_default_source_is_auto(self):
        tab = self._make_tab()

        self.assertEqual(tab._selected_source_name(), "auto")
        self.assertEqual(config.ACTIVE_SOURCE, "zh_wikipedia")

    def test_auto_display_label_maps_to_auto_source(self):
        tab = self._make_tab("自动（推荐）")

        self.assertEqual(tab._selected_source_name(), "auto")

    def test_wikidata_selection_passes_source_name(self):
        tab = self._make_tab("wikidata")
        factory = Mock()
        agent = object()
        factory.return_value = agent

        created = tab._create_agent(factory)

        self.assertIs(created, agent)
        factory.assert_called_once_with(source_name="wikidata")

    def test_nasa_selection_passes_source_name(self):
        tab = self._make_tab("nasa")
        factory = Mock()

        tab._create_agent(factory)

        factory.assert_called_once_with(source_name="nasa")

    def test_esa_selection_passes_source_name(self):
        tab = self._make_tab("esa")
        factory = Mock()

        tab._create_agent(factory)

        factory.assert_called_once_with(source_name="esa")

    def test_crawl_tab_exposes_four_source_buttons_and_debug_all_button(self):
        self.assertEqual(CrawlTab.SOURCE_BUTTON_ORDER, ("zh_wikipedia", "wikidata", "nasa", "esa"))
        self.assertEqual(CrawlTab.CLEANUP_SOURCE_ORDER, CrawlTab.SOURCE_BUTTON_ORDER)
        self.assertEqual(CrawlTab.DEFAULT_LIMIT, 80)

    def test_crawl_tab_uses_source_specific_limits_for_heavier_sources(self):
        self.assertEqual(CrawlTab._limit_for_source("zh_wikipedia"), 80)
        self.assertEqual(CrawlTab._limit_for_source("wikidata"), 80)
        self.assertEqual(CrawlTab._limit_for_source("nasa"), 120)
        self.assertEqual(CrawlTab._limit_for_source("esa"), 60)

    def test_cleanup_summary_lines_counts_deleted_and_missing_targets(self):
        deleted_dirs, deleted_files, missing_dirs, missing_files = CrawlTab._cleanup_summary_lines({
            "deleted": {"directories": ["a", "b"], "files": ["c"]},
            "missing": {"directories": ["d"], "files": ["e", "f"]},
        })

        self.assertEqual((deleted_dirs, deleted_files, missing_dirs, missing_files), (2, 1, 1, 2))

    def test_nlp_tab_defaults_to_active_source(self):
        tab = NlpTab.__new__(NlpTab)
        tab.selected_source_name = config.ACTIVE_SOURCE

        self.assertEqual(tab._nlp_source_name(), "zh_wikipedia")

    def test_nlp_tab_exposes_four_source_buttons(self):
        self.assertEqual(NlpTab.SOURCE_BUTTON_ORDER, ("zh_wikipedia", "wikidata", "nasa", "esa"))


if __name__ == "__main__":
    unittest.main()
