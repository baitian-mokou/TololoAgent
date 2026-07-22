import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preview_shadow_materialization.py"


def load_module():
    spec = importlib.util.spec_from_file_location("preview_shadow_materialization", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PreviewShadowMaterializationTests(unittest.TestCase):
    def test_preview_uses_summary_files_written_and_ignores_stale_files(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "data" / "triples" / "nasa"
            source_dir.mkdir(parents=True)
            selected_triples = source_dir / "current_triples.json"
            selected_narratives = source_dir / "current_narratives.json"
            stale_triples = source_dir / "stale_triples.json"
            selected_triples.write_text(json.dumps([{"source_name": "nasa", "schema_version": "nasa_shadow_ready_v1"}]), encoding="utf-8")
            selected_narratives.write_text(json.dumps([
                {"source_name": "nasa", "schema_version": "nasa_shadow_ready_v1"},
                {"source_name": "nasa", "schema_version": "nasa_shadow_ready_v1"},
            ]), encoding="utf-8")
            stale_triples.write_text(json.dumps([{"source_name": "nasa"}]), encoding="utf-8")
            (source_dir / "summary.json").write_text(
                json.dumps({"files_written": [str(selected_triples), str(selected_narratives)]}),
                encoding="utf-8",
            )

            report = module.build_preview_report("nasa", base_dir=root)

        self.assertEqual(report["selected"]["triple_files"], 1)
        self.assertEqual(report["selected"]["narrative_files"], 1)
        self.assertEqual(report["selected"]["triple_records"], 1)
        self.assertEqual(report["selected"]["narrative_records"], 2)
        self.assertEqual(report["ignored_stale"]["triple_files"], 1)
        self.assertEqual(Path(report["ignored_stale"]["sample_files"][0]).name, "stale_triples.json")

    def test_preview_does_not_change_active_source(self):
        module = load_module()
        import config

        before = config.ACTIVE_SOURCE
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "data" / "triples" / "wikidata"
            source_dir.mkdir(parents=True)
            (source_dir / "summary.json").write_text(json.dumps({"files_written": []}), encoding="utf-8")
            module.build_preview_report("wikidata", base_dir=root)

        self.assertEqual(config.ACTIVE_SOURCE, before)


if __name__ == "__main__":
    unittest.main()
