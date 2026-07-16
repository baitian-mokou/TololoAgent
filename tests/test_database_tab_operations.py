import unittest

from src.gui.main_window import DatabaseTab


class FakeButton:
    def __init__(self):
        self.state = "normal"

    def config(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]


class DatabaseTabOperationTests(unittest.TestCase):
    def test_db_operation_busy_state_disables_buttons(self):
        tab = object.__new__(DatabaseTab)
        tab.btn_import_neo4j = FakeButton()
        tab.btn_refresh_neo4j = FakeButton()
        tab.btn_import_chroma = FakeButton()
        tab.btn_refresh_chroma = FakeButton()
        tab.btn_clear_all = FakeButton()
        tab._db_operation_running = False

        self.assertTrue(tab._start_db_operation())
        self.assertFalse(tab._start_db_operation())
        self.assertEqual(tab.btn_import_neo4j.state, "disabled")
        self.assertEqual(tab.btn_import_chroma.state, "disabled")
        self.assertEqual(tab.btn_clear_all.state, "disabled")

        tab._finish_db_operation()

        self.assertEqual(tab.btn_import_neo4j.state, "normal")
        self.assertEqual(tab.btn_import_chroma.state, "normal")
        self.assertEqual(tab.btn_clear_all.state, "normal")


if __name__ == "__main__":
    unittest.main()
