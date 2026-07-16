import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_source_conflict_audit as audit


def write_triples(path: Path, source: str, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    enriched = []
    for record in records:
        payload = dict(record)
        payload.setdefault("source", source)
        payload.setdefault("source_name", source)
        payload.setdefault("source_role", "primary")
        payload.setdefault("origin", "html_fallback")
        payload.setdefault("schema_version", f"{source}_test")
        payload.setdefault("source_title", payload.get("subject", ""))
        enriched.append(payload)
    path.write_text(json.dumps(enriched, ensure_ascii=False), encoding="utf-8")


class SourceConflictAuditTests(unittest.TestCase):
    def test_audit_identifies_conflict_equivalence_and_missing_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            triples = root / "triples"
            write_triples(triples / "火星_triples.json", "zh_wikipedia", [
                {"subject": "火星", "relation": "HAS_MASS", "object": "6.4169 × 10 23 kg"},
                {"subject": "火星", "relation": "HAS_RADIUS", "object": "1.0 km"},
                {"subject": "火星", "relation": "HAS_ATMOSPHERE", "object": "CO2"},
                {"subject": "火星", "relation": "HAS_ATMOSPHERE", "object": "N2"},
                {"subject": "火卫一", "relation": "HAS_MASS", "object": "1.072 × 10 16 kg"},
                {"subject": "月球", "relation": "ORBITS", "object": "地球"},
                {"subject": "木星", "relation": "HAS_RADIUS", "object": "71492 km", "raw": "赤道半径: 71492 km"},
            ])
            write_triples(triples / "wikidata" / "火星_triples.json", "wikidata", [
                {"subject": "火星", "relation": "HAS_MASS", "object": "6.4171e23 kg"},
                {"subject": "火星", "relation": "HAS_RADIUS", "object": "3389.5 km"},
                {"subject": "火星", "relation": "HAS_ATMOSPHERE", "object": "二氧化碳;氮气"},
                {"subject": "火卫一", "relation": "HAS_MASS", "object": "1.0659e16 kg"},
                {"subject": "月球", "relation": "ORBITS", "object": "Q2"},
                {"subject": "木星", "relation": "HAS_RADIUS", "object": "69911 km", "raw": "mean radius"},
            ])
            write_triples(triples / "nasa" / "火星_triples.json", "nasa", [
                {"subject": "火星", "relation": "HAS_RADIUS", "object": "3389.5 km"},
            ])

            original_triples_dir = audit.TRIPLES_DIR
            original_json = audit.REPORT_JSON
            original_md = audit.REPORT_MD
            original_v2_json = audit.REPORT_V2_JSON
            original_v2_md = audit.REPORT_V2_MD
            original_v3_json = audit.REPORT_V3_JSON
            original_v3_md = audit.REPORT_V3_MD
            original_v4_json = audit.REPORT_V4_JSON
            original_v4_md = audit.REPORT_V4_MD
            original_patch_dir = audit.QUALITY_PATCH_DIR
            original_patch_candidates = audit.QUALITY_PATCH_CANDIDATES
            try:
                audit.TRIPLES_DIR = str(triples)
                audit.REPORT_JSON = str(root / "evaluation" / "source_conflict_audit.json")
                audit.REPORT_MD = str(root / "docs" / "source_conflict_audit.md")
                audit.REPORT_V2_JSON = str(root / "evaluation" / "source_conflict_audit_v2.json")
                audit.REPORT_V2_MD = str(root / "docs" / "source_conflict_audit_v2.md")
                audit.REPORT_V3_JSON = str(root / "evaluation" / "source_conflict_audit_v3.json")
                audit.REPORT_V3_MD = str(root / "docs" / "source_conflict_audit_v3.md")
                audit.REPORT_V4_JSON = str(root / "evaluation" / "source_conflict_audit_v4.json")
                audit.REPORT_V4_MD = str(root / "docs" / "source_conflict_audit_v4.md")
                audit.QUALITY_PATCH_DIR = str(root / "data" / "quality_patches")
                audit.QUALITY_PATCH_CANDIDATES = str(root / "data" / "quality_patches" / "source_conflict_resolution_candidates.json")
                report = audit.run_audit()
                report_v2 = audit.run_audit_v2(report)
                report_v3 = audit.run_audit_v3(report, report_v2)
                report_v4 = audit.run_audit_v4(report_v3)
            finally:
                audit.TRIPLES_DIR = original_triples_dir
                audit.REPORT_JSON = original_json
                audit.REPORT_MD = original_md
                audit.REPORT_V2_JSON = original_v2_json
                audit.REPORT_V2_MD = original_v2_md
                audit.REPORT_V3_JSON = original_v3_json
                audit.REPORT_V3_MD = original_v3_md
                audit.REPORT_V4_JSON = original_v4_json
                audit.REPORT_V4_MD = original_v4_md
                audit.QUALITY_PATCH_DIR = original_patch_dir
                audit.QUALITY_PATCH_CANDIDATES = original_patch_candidates

            statuses = {(item["subject"], item["relation"]): set(item["status"]) for item in report["findings"]}
            self.assertIn("unit_equivalent", statuses[("火星", "HAS_MASS")])
            self.assertIn("value_conflict", statuses[("火星", "HAS_RADIUS")])
            self.assertIn("source_missing", statuses[("火星", "HAS_ATMOSPHERE")])
            self.assertTrue((root / "docs" / "source_conflict_audit.md").exists())
            statuses_v2 = {(item["subject"], item["relation"]): set(item["status"]) for item in report_v2["findings"]}
            self.assertIn("unit_equivalent", statuses_v2[("火星", "HAS_MASS")])
            self.assertIn("likely_zhwiki_extraction_error", statuses_v2[("火星", "HAS_RADIUS")])
            self.assertIn("synonym_equivalent", statuses_v2[("火星", "HAS_ATMOSPHERE")])
            self.assertIn("value_conflict", statuses_v2[("火卫一", "HAS_MASS")])
            self.assertEqual(report_v2["summary"]["metadata_incomplete_count"], 0)
            self.assertTrue((root / "docs" / "source_conflict_audit_v2.md").exists())
            statuses_v3 = {(item["subject"], item["relation"]): set(item["status"]) for item in report_v3["findings"]}
            self.assertIn("entity_alias_equivalent", statuses_v3[("月球", "ORBITS")])
            self.assertIn("same_quantity_different_measurement_kind", statuses_v3[("木星", "HAS_RADIUS")])
            self.assertIn("radius_kind_mismatch", statuses_v3[("木星", "HAS_RADIUS")])
            self.assertNotIn("value_conflict", statuses_v3[("木星", "HAS_RADIUS")])
            self.assertEqual(report_v3["summary"]["metadata_incomplete_count"], 0)
            self.assertTrue((root / "docs" / "source_conflict_audit_v3.md").exists())
            self.assertEqual(report_v4["summary"]["metadata_incomplete_count"], 0)
            self.assertEqual(report_v4["summary"]["evidence_packet_count"], report_v3["summary"]["value_conflict_count"])
            self.assertEqual(report_v4["summary"]["quality_patch_candidate_count"], report_v4["summary"]["evidence_packet_count"])
            self.assertTrue((root / "data" / "quality_patches" / "source_conflict_resolution_candidates.json").exists())


if __name__ == "__main__":
    unittest.main()
