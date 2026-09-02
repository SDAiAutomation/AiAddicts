import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.script import load_script, slug, validate_script

VALID = {
    "title": "Titre de test",
    "niche": "coach-business",
    "account": "test-account-01",
    "voice_id": "abc123",
    "blocks": [
        {"role": "hook", "text": "Une accroche"},
        {"role": "cta", "text": "Un appel à l'action"},
    ],
}


def write_json(data):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, f)
    f.close()
    return f.name


class TestValidateScript(unittest.TestCase):
    def test_valid_script_passes(self):
        validate_script(VALID)  # no exception

    def test_missing_title_raises(self):
        data = dict(VALID)
        del data["title"]
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_empty_blocks_raises(self):
        data = {**VALID, "blocks": []}
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_block_missing_text_raises(self):
        data = {**VALID, "blocks": [{"role": "hook", "text": ""}]}
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_block_invalid_role_raises(self):
        data = {**VALID, "blocks": [{"role": "outro", "text": "x"}]}
        with self.assertRaises(ValueError):
            validate_script(data)


class TestLoadScript(unittest.TestCase):
    def test_load_script_fills_defaults(self):
        path = write_json(VALID)
        data = load_script(path)
        self.assertEqual(data["aspect_ratio"], "9:16")
        self.assertEqual(data["hashtags"], [])


class TestSlug(unittest.TestCase):
    def test_slug_is_filesystem_safe(self):
        s = slug({"account": "Test Account!", "title": "L'erreur n°1"})
        self.assertNotIn(" ", s)
        self.assertNotIn("'", s)
        self.assertNotIn("°", s)
        self.assertTrue(s.startswith("test-account"))


if __name__ == "__main__":
    unittest.main()
