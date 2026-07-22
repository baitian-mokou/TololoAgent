import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_small_batch_command_skeleton.py"


def load_module():
    spec = importlib.util.spec_from_file_location("render_small_batch_command_skeleton", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmallBatchCommandSkeletonTests(unittest.TestCase):
    def sample_plan(self, root: Path, items=None) -> Path:
        payload = {
            "mode": "approved_small_batch_plan_preview",
            "execution_status": "not_run",
            "network": False,
            "formal_pipeline_write": False,
            "items": items if items is not None else [{
                "source_id": "official_science_example",
                "approved_sample_size": 12,
                "candidate_count": 4,
                "selected_candidate_urls": ["https://agency.example.gov/solar-system/mars-fact-sheet"],
                "selected_candidate_titles": ["Mars Fact Sheet"],
                "execution_status": "not_run",
                "blocked_until": "manual command",
            }],
        }
        path = root / "evaluation" / "source_quality" / "sandbox" / "plan.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_renders_manual_not_executed_skeleton(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self.sample_plan(root)
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "skeleton.json"
            out_md = root / "evaluation" / "source_quality" / "sandbox" / "skeleton.md"

            exit_code = module.main([
                "--plan-json",
                str(plan),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            item = payload["items"][0]
            self.assertTrue(item["manual_approval_required"])
            self.assertEqual(item["execution_status"], "not_run")
            self.assertIn("NOT EXECUTED", item["proposed_command"])
            self.assertIn("DRY RUN", item["proposed_command"])
            self.assertIn("ACTIVE_SOURCE unchanged", item["safety_guards"])
            self.assertFalse((root / "data").exists())
            markdown = out_md.read_text(encoding="utf-8")
            self.assertIn("NOT EXECUTED", markdown)
            self.assertIn("manual approval", markdown.lower())

    def test_empty_plan_renders_empty_skeleton(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self.sample_plan(root, items=[])
            out_json = root / "evaluation" / "source_quality" / "sandbox" / "empty.json"
            exit_code = module.main(["--plan-json", str(plan), "--out-json", str(out_json)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["command_skeletons"], 0)
            self.assertEqual(payload["items"], [])

    def test_outputs_must_stay_under_sandbox(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = self.sample_plan(root)
            bad = root / "data" / "skeleton.json"
            exit_code = module.main(["--plan-json", str(plan), "--out-json", str(bad)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(bad.exists())

    def test_script_source_has_no_network_ingest_or_delete_calls(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("ingest_frontier", source)
        self.assertNotIn("clear_source_ingestion_outputs", source)
        self.assertNotIn("shutil.rmtree", source)
        self.assertNotIn("os.remove", source)


if __name__ == "__main__":
    unittest.main()
