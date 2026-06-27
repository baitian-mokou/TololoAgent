import unittest

from scripts.run_source_conflict_audit import build_quality_patch_candidates


class QualityPatchCandidateTests(unittest.TestCase):
    def test_candidates_require_human_approval_and_do_not_apply(self):
        candidates = build_quality_patch_candidates([
            {
                "subject": "金星",
                "relation": "HAS_RADIUS",
                "audit_classification": "zhwiki_extraction_error",
                "values_by_source": {"zh_wikipedia": ["1.0km"], "wikidata": ["6051.8 km"]},
                "evidence_by_source": {
                    "zh_wikipedia": [{
                        "target_file": "data/triples/金星_triples.json",
                        "target_record_hint": {"subject": "金星", "relation": "HAS_RADIUS", "object": "1.0km"},
                    }]
                },
                "reason": "implausible radius",
                "confidence": 0.86,
            }
        ])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["action"], "mark_extraction_error")
        self.assertTrue(candidates[0]["requires_human_approval"])
        self.assertIn("before", candidates[0])
        self.assertIn("after", candidates[0])


if __name__ == "__main__":
    unittest.main()
