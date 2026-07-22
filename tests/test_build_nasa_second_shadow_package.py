import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_nasa_second_shadow_package.py"


def load_script():
    spec = importlib.util.spec_from_file_location("build_nasa_second_shadow_package", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NasaSecondShadowPackageTests(unittest.TestCase):
    def write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def make_phase40_and_phase45(self, root: Path) -> tuple[Path, Path]:
        phase40 = root / "evaluation" / "four_source_expansion" / "deduped.json"
        phase45 = root / "evaluation" / "four_source_expansion" / "phase45"
        self.write_json(
            phase40,
            {
                "sources": [
                    {
                        "source_id": "nasa",
                        "selected_candidates": [
                            {
                                "title": "already packaged",
                                "url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                                "source_reason": "accepted",
                            },
                            {
                                "title": "Comet Example",
                                "url": "https://science.nasa.gov/solar-system/comets/example/",
                                "source_reason": "accepted",
                            },
                            {
                                "title": "Mission Example",
                                "url": "https://science.nasa.gov/mission/example/",
                                "source_reason": "accepted",
                            },
                            {
                                "title": "https://nssdc.gsfc.nasa.gov/planetary/planets/cometpage.html",
                                "url": "https://nssdc.gsfc.nasa.gov/planetary/planets/cometpage.html",
                                "source_reason": "accepted",
                            },
                        ],
                    }
                ]
            },
        )
        self.write_json(
            phase45 / "triples_preview.json",
            [
                {
                    "subject": "Apophis",
                    "predicate": "SOURCE_URL",
                    "object": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                    "source_url": "https://science.nasa.gov/solar-system/asteroids/apophis/",
                },
                {
                    "subject": "NASA Space Science Data Coordinated Archive Status",
                    "predicate": "SOURCE_URL",
                    "object": "https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html",
                    "source_url": "https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html",
                }
            ],
        )
        return phase40, phase45

    def fake_fetcher(self, url: str, timeout: int):
        if "nssdc" in url:
            title = "NASA Space Science Data Coordinated Archive Status"
        else:
            title = "Comet Example" if "comets" in url else "Mission Example"
        science_text = " ".join(
            [
                "NASA science solar system planetary science mission asteroid comet spacecraft orbit discovery diameter exploration data research observations",
                "This official NASA overview describes a solar system small body with mission observations and science facts.",
            ]
            * 12
        )
        body = (
            f"<html><head><title>{title} - NASA Science</title></head><body>"
            f"<h1>{title}</h1><p>{title} is a NASA comet mission page. "
            "The comet has a diameter of 5 km and was discovered by Jane Doe. "
            f"NASA mission spacecraft observations describe this solar system object. {science_text}</p>"
            "</body></html>"
        )
        return {"url": url, "content_type": "text/html", "body": body}

    def test_second_package_excludes_phase45_and_builds_pending_package(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase40, phase45 = self.make_phase40_and_phase45(root)
            out_dir = root / "evaluation" / "four_source_expansion" / "phase52"
            approval = root / "evaluation" / "four_source_expansion" / "approval.json"

            report = module.build_second_package(
                phase40_json=phase40,
                phase45_package_dir=phase45,
                out_dir=out_dir,
                approval_template=approval,
                target_count=30,
                fetcher=self.fake_fetcher,
            )

            urls = {item["source_url"] for item in report["sample_items"]}
            titles = {item["title"] for item in report["sample_items"]}
            self.assertNotIn("https://science.nasa.gov/solar-system/asteroids/apophis/", urls)
            self.assertNotIn("NASA Space Science Data Coordinated Archive Status", titles)
            self.assertEqual(report["selected_count"], 3)
            self.assertEqual(report["packaged_items"], 2)
            self.assertEqual(report["phase45_items_excluded"], 2)
            self.assertGreaterEqual(report["triples"], 6)
            self.assertGreaterEqual(report["narratives"], 2)
            self.assertEqual(report["approval_status"], "pending")
            approval_payload = json.loads(approval.read_text(encoding="utf-8"))
            self.assertEqual(approval_payload["approval_decision"], "pending")
            self.assertFalse((root / "data" / "triples").exists())
            self.assertFalse(report["formal_triples_write"])
            self.assertFalse(report["chroma_write"])
            self.assertFalse(report["neo4j_write"])

    def test_rejects_outputs_outside_evaluation(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase40, phase45 = self.make_phase40_and_phase45(root)
            exit_code = module.main(
                [
                    "--phase40-json",
                    str(phase40),
                    "--phase45-package-dir",
                    str(phase45),
                    "--out-dir",
                    str(root / "data" / "bad"),
                    "--report-json",
                    str(root / "evaluation" / "four_source_expansion" / "report.json"),
                    "--report-md",
                    str(root / "docs" / "report.md"),
                    "--approval-template",
                    str(root / "evaluation" / "four_source_expansion" / "approval.json"),
                ]
            )
            self.assertEqual(exit_code, 2)

    def test_third_package_excludes_phase45_and_phase52_overlap(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            phase40, phase45 = self.make_phase40_and_phase45(root)
            phase52 = root / "evaluation" / "four_source_expansion" / "phase52"
            self.write_json(
                phase52 / "triples_preview.json",
                [
                    {
                        "subject": "Comet Example",
                        "predicate": "SOURCE_URL",
                        "object": "https://science.nasa.gov/solar-system/comets/example/",
                        "source_url": "https://science.nasa.gov/solar-system/comets/example/",
                    }
                ],
            )
            self.write_json(phase52 / "narratives_preview.json", [])
            phase52_report = root / "evaluation" / "four_source_expansion" / "phase52_report.json"
            self.write_json(
                phase52_report,
                {
                    "candidate_statuses": [
                        {
                            "status": "duplicate_skipped",
                            "title": "Mission Example",
                            "url": "https://science.nasa.gov/mission/example/",
                        }
                    ]
                },
            )

            report = module.build_nasa_package(
                phase40_json=phase40,
                exclude_package_dirs=[phase45, phase52],
                exclude_report_paths=[phase52_report],
                out_dir=root / "evaluation" / "four_source_expansion" / "phase57",
                approval_template=root / "evaluation" / "four_source_expansion" / "approval57.json",
                target_count=50,
                phase_label="Phase 57",
                package_name="nasa_third_shadow_package_phase57",
                mode="nasa_third_shadow_package_preparation",
                fetcher=self.fake_fetcher,
            )

            titles = {item["title"] for item in report["sample_items"]}
            self.assertNotIn("Comet Example", titles)
            self.assertNotIn("Mission Example", titles)
            self.assertEqual(report["selected_count"], 1)
            self.assertEqual(report["packaged_items"], 0)
            self.assertEqual(report["prior_items_excluded_after_fetch"], 1)
            self.assertEqual(report["approval_status"], "pending")
            self.assertFalse(report["formal_triples_write"])


if __name__ == "__main__":
    unittest.main()
