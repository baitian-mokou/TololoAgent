import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.validate_ingestion_outputs import validate_ingestion_outputs


class ValidateIngestionOutputsTests(unittest.TestCase):
    def test_reports_missing_source_as_incomplete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_root = root / "data" / "raw_json"
            triples_root = root / "data" / "triples"
            evaluation_root = root / "evaluation" / "ingestion"

            (raw_root / "zh_wikipedia").mkdir(parents=True)
            (triples_root / "zh_wikipedia").mkdir(parents=True)
            evaluation_root.mkdir(parents=True)
            (raw_root / "zh_wikipedia" / "金星.json").write_text("{}", encoding="utf-8")
            (triples_root / "zh_wikipedia" / "金星_triples.json").write_text("[]", encoding="utf-8")
            (evaluation_root / "zh_wikipedia_ingestion_report.json").write_text(json.dumps({
                "source": "zh_wikipedia",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False), encoding="utf-8")

            result = validate_ingestion_outputs(
                ["zh_wikipedia", "esa"],
                raw_root=str(raw_root),
                triples_root=str(triples_root),
                evaluation_root=str(evaluation_root),
            )

        self.assertFalse(result["passed"])
        self.assertIn("esa", result["incomplete_sources"])

    def test_stale_report_is_marked_incomplete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_root = root / "data" / "raw_json"
            triples_root = root / "data" / "triples"
            evaluation_root = root / "evaluation" / "ingestion"

            raw_dir = raw_root / "nasa"
            triples_dir = triples_root / "nasa"
            raw_dir.mkdir(parents=True)
            triples_dir.mkdir(parents=True)
            evaluation_root.mkdir(parents=True)

            raw_file = raw_dir / "火星.json"
            triples_file = triples_dir / "火星_triples.json"
            report_file = evaluation_root / "nasa_ingestion_report.json"

            raw_file.write_text("{}", encoding="utf-8")
            triples_file.write_text("[]", encoding="utf-8")
            stale_time = datetime.now(timezone.utc) - timedelta(hours=1)
            report_file.write_text(json.dumps({
                "source": "nasa",
                "generated_at": stale_time.isoformat(),
            }, ensure_ascii=False), encoding="utf-8")

            fresh_epoch = datetime.now(timezone.utc).timestamp()
            os.utime(raw_file, (fresh_epoch, fresh_epoch))
            os.utime(triples_file, (fresh_epoch, fresh_epoch))

            result = validate_ingestion_outputs(
                ["nasa"],
                raw_root=str(raw_root),
                triples_root=str(triples_root),
                evaluation_root=str(evaluation_root),
            )

        self.assertFalse(result["passed"])
        self.assertEqual(result["incomplete_sources"], ["nasa"])
        nasa_check = result["source_checks"][0]
        self.assertIn("stale_ingestion_report", nasa_check["issues"])


if __name__ == "__main__":
    unittest.main()
