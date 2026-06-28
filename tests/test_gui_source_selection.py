import unittest
from unittest.mock import Mock

import config
from src.gui.main_window import AgentTab
from src.source_router import SourceRouterPreview


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

    def test_default_source_stays_zh_wikipedia(self):
        tab = self._make_tab()

        self.assertEqual(tab._selected_source_name(), "zh_wikipedia")
        self.assertEqual(config.ACTIVE_SOURCE, "zh_wikipedia")

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

    def test_source_router_stays_disabled_by_default(self):
        trace = SourceRouterPreview().route("火星质量是多少")

        self.assertFalse(trace["enabled"])
        self.assertEqual(config.ACTIVE_SOURCE, "zh_wikipedia")


if __name__ == "__main__":
    unittest.main()
