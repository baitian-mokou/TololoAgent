import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_wikidata_shadow_readiness_phase78.py"


def load_module():
    spec = importlib.util.spec_from_file_location("report_wikidata_shadow_readiness_phase78", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WikidataShadowReadinessPhase78Tests(unittest.TestCase):
    def make_shadow_dir(self, root: Path, *, items=1, triples_count=2, narratives_count=1) -> Path:
        shadow = root / "data" / "triples_shadow" / "wikidata"
        shadow.mkdir(parents=True)
        triples = [
            {"subject": "火星", "predicate": "ORBITS", "object": "太阳", "qid": "Q111", "source_url": "https://www.wikidata.org/wiki/Q111", "source_id": "wikidata", "schema_version": "wikidata_shadow_ready_v1"},
            {"subject": "火星", "predicate": "HAS_MASS", "object": "6.4e23 kg", "qid": "Q111", "source_url": "https://www.wikidata.org/wiki/Q111", "source_id": "wikidata", "schema_version": "wikidata_shadow_ready_v1"},
        ][:triples_count]
        narratives = [{"page_title": "火星", "content": "火星 orbit narrative", "qid": "Q111", "source_url": "https://www.wikidata.org/wiki/Q111", "source_id": "wikidata", "schema_version": "wikidata_shadow_ready_v1"}][:narratives_count]
        (shadow / "triples_preview.json").write_text(json.dumps(triples), encoding="utf-8")
        (shadow / "narratives_preview.json").write_text(json.dumps(narratives), encoding="utf-8")
        (shadow / "package_manifest.json").write_text(json.dumps({"source_id": "wikidata", "items": items, "triples": triples_count, "narratives": narratives_count}), encoding="utf-8")
        return shadow

    def test_missing_shadow_files_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            report = module.build_report(shadow_dir=Path(temp) / "data" / "triples_shadow" / "wikidata")
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "missing_shadow_files")

    def test_count_mismatch_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            shadow = self.make_shadow_dir(Path(temp))
            report = module.build_report(shadow_dir=shadow)
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "count_mismatch")

    def test_eval_passes_with_expected_counts_and_schema(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            shadow = self.make_shadow_dir(Path(temp))
            report = module.build_report(
                shadow_dir=shadow,
                cases=[{"case_id": "mars", "query": "火星 Q111", "oracle": {"subject": "火星", "qid": "Q111"}}],
                expected_items=1,
                expected_triples=2,
                expected_narratives=1,
            )
            self.assertTrue(report["ready"])
            self.assertEqual(report["eval"]["overall"]["pass_rate"], 1.0)
            self.assertEqual(report["validation"]["triple_qid_present"], 2)
            self.assertFalse((Path(temp) / "data" / "triples").exists())
            self.assertFalse((Path(temp) / "data" / "chroma_db").exists())

    def test_schema_or_qid_missing_blocks(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            shadow = self.make_shadow_dir(Path(temp))
            triples = json.loads((shadow / "triples_preview.json").read_text(encoding="utf-8"))
            triples[0].pop("qid")
            (shadow / "triples_preview.json").write_text(json.dumps(triples), encoding="utf-8")
            report = module.build_report(shadow_dir=shadow, expected_items=1, expected_triples=2, expected_narratives=1)
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "metadata_mismatch")

    def test_output_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(ROOT / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(outside / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()
