import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.publish_pack import build_caption, build_checklist, write_pack

SCRIPT = {
    "title": "L'erreur n°1",
    "account": "test-account-01",
    "aspect_ratio": "9:16",
    "hashtags": ["#a", "#b"],
    "blocks": [
        {"role": "hook", "text": "L'accroche"},
        {"role": "point", "text": "Un point"},
        {"role": "cta", "text": "Le CTA"},
    ],
}


class TestBuildCaption(unittest.TestCase):
    def test_hook_cta_and_hashtags(self):
        caption = build_caption(SCRIPT)
        self.assertEqual(caption, "L'accroche\n\nLe CTA\n\n#a #b")

    def test_explicit_cta_field_wins(self):
        caption = build_caption({**SCRIPT, "cta": "CTA explicite"})
        self.assertIn("CTA explicite", caption)
        self.assertNotIn("Le CTA", caption)

    def test_no_hashtags(self):
        caption = build_caption({**SCRIPT, "hashtags": []})
        self.assertEqual(caption, "L'accroche\n\nLe CTA")


class TestBuildChecklist(unittest.TestCase):
    def test_includes_log_metrics_command_with_id(self):
        md = build_checklist(SCRIPT, "output/x/final/x.mp4", "abc-123")
        self.assertIn("log_metrics.py abc-123 --mark-published", md)
        self.assertNotIn("suivi-hebdo.csv", md)

    def test_generic_line_without_id(self):
        md = build_checklist(SCRIPT, "output/x/final/x.mp4")
        self.assertIn("log_metrics.py", md)
        self.assertNotIn("suivi-hebdo.csv", md)


class TestWritePack(unittest.TestCase):
    def test_writes_both_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = write_pack(SCRIPT, "v.mp4", d, "cid-1")
            self.assertTrue(Path(out["caption"]).is_file())
            self.assertTrue(Path(out["checklist"]).is_file())
            self.assertIn("cid-1", Path(out["checklist"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
