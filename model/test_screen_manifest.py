import json,tempfile,unittest
from pathlib import Path
from screen import ensure_manifest,prefilter


class Manifest(unittest.TestCase):
    def test_same_revision_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);ensure_manifest(p,'2026-11-16');ensure_manifest(p,'2026-11-16')
            with self.assertRaises(ValueError):ensure_manifest(p,'2026-11-17')
    def test_legacy_outputs_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'raw.jsonl').write_text('{}\n')
            with self.assertRaises(ValueError):ensure_manifest(p,'2026-11-16')
            self.assertEqual((p/'raw.jsonl').read_text(),'{}\n')
    def test_no_quotes(self):
        self.assertEqual(prefilter([]),([],{'无有效报价':0},None))
