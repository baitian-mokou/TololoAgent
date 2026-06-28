import unittest

from src.source_quality.cross_source_fusion import fuse_cross_source_records


class CrossSourceValueFusionTests(unittest.TestCase):
    def test_identical_values_merge_without_human_review(self):
        report = fuse_cross_source_records([
            {"subject": "火星", "relation": "HAS_MASS", "object": "6.4171e23 kg", "source_name": "nasa"},
            {"subject": "火星", "relation": "HAS_MASS", "object": "6.4171e23 kg", "source_name": "wikidata"},
        ])

        self.assertEqual(report["summary"]["multi_source_agreement_count"], 1)
        self.assertEqual(report["summary"]["human_review_required_count"], 0)
        fused = report["fused_records"][0]
        self.assertEqual(fused["fusion_status"], "multi_source_agreement")
        self.assertEqual(set(fused["sources"]), {"nasa", "wikidata"})

    def test_unit_equivalent_values_merge_without_human_review(self):
        report = fuse_cross_source_records([
            {"subject": "火星", "relation": "HAS_RADIUS", "object": "3389.5 km", "source_name": "nasa"},
            {"subject": "火星", "relation": "HAS_RADIUS", "object": "3389500 m", "source_name": "wikidata"},
        ])

        self.assertEqual(report["summary"]["multi_source_agreement_count"], 1)
        self.assertEqual(report["summary"]["human_review_required_count"], 0)

    def test_near_equivalent_values_are_preserved_without_review(self):
        report = fuse_cross_source_records([
            {"subject": "火卫一", "relation": "HAS_RADIUS", "object": "11.1 km", "source_name": "zh_wikipedia"},
            {"subject": "火卫一", "relation": "HAS_RADIUS", "object": "11.2 km", "source_name": "wikidata"},
        ])

        self.assertEqual(report["summary"]["near_equivalent_values_count"], 1)
        self.assertEqual(report["summary"]["human_review_required_count"], 0)
        statuses = {item["fusion_status"] for item in report["fused_records"]}
        self.assertEqual(statuses, {"near_equivalent_values"})

    def test_measurement_kind_difference_does_not_enter_review(self):
        report = fuse_cross_source_records([
            {
                "subject": "木星",
                "relation": "HAS_RADIUS",
                "object": "69911 km",
                "source_name": "nasa",
                "source_title": "Jupiter",
                "source_field": "Mean radius (km)",
            },
            {
                "subject": "木星",
                "relation": "HAS_RADIUS",
                "object": "71492 km",
                "source_name": "wikidata",
                "source_title": "木星",
                "source_field": "equatorial radius",
            },
        ])

        self.assertEqual(report["summary"]["measurement_kind_difference_count"], 1)
        self.assertEqual(report["summary"]["human_review_required_count"], 0)

    def test_large_difference_requires_human_review(self):
        report = fuse_cross_source_records([
            {"subject": "金星", "relation": "HAS_RADIUS", "object": "1.0 km", "source_name": "zh_wikipedia"},
            {"subject": "金星", "relation": "HAS_RADIUS", "object": "6051.8 km", "source_name": "wikidata"},
        ])

        self.assertEqual(report["summary"]["human_review_required_count"], 1)
        self.assertEqual(len(report["review_candidates"]), 1)
        self.assertEqual(report["review_candidates"][0]["relation"], "HAS_RADIUS")


if __name__ == "__main__":
    unittest.main()
