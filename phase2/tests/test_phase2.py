from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from krutidev import decode_kruti_label, split_bilingual_label
from run_pipeline import load_manifest, number
import source_paths
from source_paths import resolve_source_path


class Phase2CoreTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(number("13,490.2"), 13490.2)
        self.assertIsNone(number("N.A."))

    def test_krutidev_from_basic_statistics(self):
        self.assertEqual(decode_kruti_label("Qlyksa dk uke"), "फसलों का नाम")
        self.assertEqual(decode_kruti_label("Ukkfj;y"), "नारियल")
        self.assertEqual(decode_kruti_label("/kku"), "धान")
        self.assertEqual(decode_kruti_label("nf{k.k v.Meku"), "दक्षिण अण्डमान")

    def test_bilingual_row(self):
        self.assertEqual(split_bilingual_label("Ukkfj;y Coconut (M/nuts)"),
                         ("नारियल", "Coconut (M/nuts)"))

    def test_manifest_has_only_bundled_source_documents(self):
        manifest = load_manifest()
        self.assertEqual(len(manifest), 17)
        for item in manifest:
            path = resolve_source_path(item["relative_path"])
            self.assertTrue(path.exists(), item["relative_path"])

    def test_course_repository_uses_existing_phase1_folder(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as tmp:
            repo = Path(tmp)
            phase2_root = repo / "Phase 2" / "Phase2_Submission"
            phase2_root.mkdir(parents=True)
            source = repo / "Phase 1" / "basic stats" / "example.pdf"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"test source")
            with patch.object(source_paths, "PHASE2_ROOT", phase2_root):
                self.assertEqual(resolve_source_path("basic stats/example.pdf"), source)


if __name__ == "__main__":
    unittest.main()
