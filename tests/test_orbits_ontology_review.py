import tempfile
import unittest
from pathlib import Path

from scripts.run_external_source_review import write_orbits_review


class OrbitsOntologyReviewTests(unittest.TestCase):
    def test_orbits_review_documents_entity_object_validation_rule(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "orbits_ontology_review.md"

            write_orbits_review(str(path))
            text = path.read_text(encoding="utf-8")

            self.assertIn("ORBITS object must be a known celestial-body entity", text)
            self.assertIn("Descriptive phrases are invalid ORBITS objects", text)
            self.assertIn("extraction_error_candidate", text)
            self.assertIn("No formal ontology change is applied", text)


if __name__ == "__main__":
    unittest.main()
