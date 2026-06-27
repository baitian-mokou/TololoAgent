import unittest

from src import source_control


class SourceControlRegistrationTests(unittest.TestCase):
    def test_wikidata_formal_registration_is_separate_from_active_source(self):
        registration = source_control.get_formal_source_registration("wikidata")

        self.assertTrue(registration["is_formally_integrated"])
        self.assertEqual(registration["materialization_status"], "graph_embedding_materialized")
        self.assertFalse(registration["cutover_ready"])
        self.assertEqual(registration["approval_mode"], "owner-approved exception")
        self.assertEqual(registration["registry_status"], "disabled")
        self.assertFalse(source_control.is_active_source("wikidata"))


if __name__ == "__main__":
    unittest.main()
