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

    def test_invalid_platform_raises(self):
        data = {**VALID, "platform": "facebook"}
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_missing_platform_is_valid(self):
        validate_script(VALID)  # platform is optional at validation time, defaulted on load

    def test_caption_style_optional_and_validated(self):
        validate_script(VALID)  # absent -> OK
        validate_script({**VALID, "caption_style": "word_pop"})  # connu -> OK
        with self.assertRaises(ValueError):
            validate_script({**VALID, "caption_style": "rainbow"})

    def test_characters_optional(self):
        validate_script(VALID)  # pas de 'characters' -> OK

    def test_valid_characters_pass(self):
        data = {**VALID, "characters": [
            {"name": "Léo", "description": "un ourson brun", "negative": "jamais humain"},
        ]}
        validate_script(data)  # no exception

    def test_character_without_name_raises(self):
        data = {**VALID, "characters": [{"description": "un ourson brun"}]}
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_character_without_description_raises(self):
        data = {**VALID, "characters": [{"name": "Léo"}]}
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_characters_not_a_list_raises(self):
        data = {**VALID, "characters": {"name": "Léo", "description": "x"}}
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_invalid_aspect_ratio_raises(self):
        data = {**VALID, "aspect_ratio": "4:5"}
        with self.assertRaises(ValueError):
            validate_script(data)

    def test_missing_aspect_ratio_is_valid(self):
        validate_script(VALID)  # optional at validation time, defaulted on load

    def test_language_optional_and_validated(self):
        validate_script(VALID)  # absent -> OK
        validate_script({**VALID, "language": "en"})  # connu -> OK
        with self.assertRaises(ValueError):
            validate_script({**VALID, "language": "klingon"})


class TestLoadScript(unittest.TestCase):
    def test_load_script_fills_defaults(self):
        path = write_json(VALID)
        data = load_script(path)
        self.assertEqual(data["aspect_ratio"], "9:16")
        self.assertEqual(data["hashtags"], [])
        self.assertEqual(data["platform"], "tiktok")
        self.assertEqual(data["organization"], "GrowthOS Dogfooding")
        self.assertEqual(data["language"], "fr")


class TestSlug(unittest.TestCase):
    def test_slug_is_filesystem_safe(self):
        s = slug({"account": "Test Account!", "title": "L'erreur n°1"})
        self.assertNotIn(" ", s)
        self.assertNotIn("'", s)
        self.assertNotIn("°", s)
        self.assertTrue(s.startswith("test-account"))

    def test_slug_falls_back_when_no_alphanumeric(self):
        self.assertEqual(slug({"account": "!!!", "title": "??? °°°"}), "script")


if __name__ == "__main__":
    unittest.main()
