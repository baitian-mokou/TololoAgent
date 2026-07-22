import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_esa_shadow_readiness_phase72.py"


def load_module():
    spec = importlib.util.spec_from_file_location("report_esa_shadow_readiness_phase72", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EsaShadowReadinessPhase72Tests(unittest.TestCase):
    def make_shadow_dir(self, root: Path, *, items=1, triples_count=3, narratives_count=2) -> Path:
        shadow = root / "data" / "triples_shadow" / "esa"
        shadow.mkdir(parents=True)
        triples = [
            {"subject": "Rosetta", "predicate": "SOURCE_URL", "object": "https://www.esa.int/rosetta", "source_url": "https://www.esa.int/rosetta", "evidence": "https://www.esa.int/rosetta", "validation_status": "accepted", "source_id": "esa"},
            {"subject": "Rosetta", "predicate": "HAS_TOPIC", "object": "space science mission", "source_url": "https://www.esa.int/rosetta", "evidence": "Rosetta is an ESA mission.", "validation_status": "accepted", "source_id": "esa"},
            {"subject": "Rosetta", "predicate": "INSTANCE_OF", "object": "ESA space science page", "source_url": "https://www.esa.int/rosetta", "evidence": "Rosetta is an ESA mission.", "validation_status": "accepted", "source_id": "esa"},
        ][:triples_count]
        narratives = [
            {"page_title": "ESA - Rosetta", "content": "Rosetta is an ESA space science mission.", "source_id": "esa", "source_role": "primary", "source_url": "https://www.esa.int/rosetta"},
            {"page_title": "ESA - Rosetta", "content": "The Rosetta spacecraft studied a comet.", "source_id": "esa", "source_role": "primary", "source_url": "https://www.esa.int/rosetta"},
        ][:narratives_count]
        (shadow / "triples_preview.json").write_text(json.dumps(triples), encoding="utf-8")
        (shadow / "narratives_preview.json").write_text(json.dumps(narratives), encoding="utf-8")
        (shadow / "package_manifest.json").write_text(json.dumps({"source_id": "esa", "items": items, "triples": triples_count, "narratives": narratives_count}), encoding="utf-8")
        return shadow

    def test_missing_shadow_files_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            report = module.build_report(shadow_dir=Path(temp) / "data" / "triples_shadow" / "esa")
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "missing_shadow_files")

    def test_count_mismatch_blocked(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            shadow = self.make_shadow_dir(Path(temp))
            report = module.build_report(shadow_dir=shadow)
            self.assertFalse(report["ready"])
            self.assertEqual(report["blocked_reason"], "count_mismatch")

    def test_eval_passes_with_expected_counts(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            shadow = self.make_shadow_dir(Path(temp))
            report = module.build_report(
                shadow_dir=shadow,
                cases=[{"case_id": "rosetta", "query": "Rosetta mission", "oracle": {"subject": "Rosetta", "topic": "mission"}}],
            )
            module.EXPECTED_ITEMS = 1
            module.EXPECTED_TRIPLES = 3
            module.EXPECTED_NARRATIVES = 2
            report = module.build_report(
                shadow_dir=shadow,
                cases=[{"case_id": "rosetta", "query": "Rosetta mission", "oracle": {"subject": "Rosetta", "topic": "mission"}}],
            )
            self.assertTrue(report["ready"])
            self.assertEqual(report["eval"]["overall"]["pass_rate"], 1.0)
            self.assertFalse((Path(temp) / "data" / "triples").exists())
            self.assertFalse((Path(temp) / "data" / "chroma_db").exists())

    def test_output_restricted(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp)
            self.assertTrue(module.output_allowed(ROOT / "evaluation" / "four_source_expansion" / "x.json"))
            self.assertTrue(module.output_allowed(ROOT / "docs" / "x.md", allow_docs=True))
            self.assertFalse(module.output_allowed(outside / "docs" / "x.md", allow_docs=True))


if __name__ == "__main__":
    unittest.main()
