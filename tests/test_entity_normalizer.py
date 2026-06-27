import unittest

from src.source_quality.entity_normalizer import entity_groups_equivalent, normalize_entity


class EntityNormalizerTests(unittest.TestCase):
    def test_normalizes_chinese_english_and_qid_aliases(self):
        self.assertEqual(normalize_entity("月球")["canonical_id"], "Q405")
        self.assertEqual(normalize_entity("Moon")["canonical_id"], "Q405")
        self.assertEqual(normalize_entity("Q405")["canonical_label"], "月球")
        self.assertTrue(entity_groups_equivalent({
            "zh_wikipedia": ["地球"],
            "wikidata": ["Q2"],
            "nasa": ["Earth"],
        }))


if __name__ == "__main__":
    unittest.main()
