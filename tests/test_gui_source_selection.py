import unittest
from unittest.mock import Mock

import config
from src.gui.main_window import AgentTab


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


if __name__ == "__main__":
    unittest.main()
