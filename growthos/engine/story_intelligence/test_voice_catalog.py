import unittest
from growthos.engine.story_intelligence.voice_catalog import resolve_character_voices


class VoiceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.story = {"characters": [{"id": "neo"}, {"id": "orion"}]}
        self.catalog = [{"id": "existing_voice_1", "name": "Corentin"}, {"id": "existing_voice_2", "name": "Paul"}]
        self.selections = {"neo": "existing_voice_1", "orion": "existing_voice_2"}

    def test_existing_catalog_voices(self):
        self.assertEqual(resolve_character_voices(self.story, self.catalog, self.selections), self.selections)

    def test_unavailable_voice_rejected(self):
        self.selections["neo"] = "unknown"
        with self.assertRaises(ValueError):
            resolve_character_voices(self.story, self.catalog, self.selections)

    def test_disabled_voice_rejected(self):
        self.catalog[1]["enabled"] = False
        with self.assertRaises(ValueError):
            resolve_character_voices(self.story, self.catalog, self.selections)

    def test_missing_character_selection_rejected(self):
        del self.selections["orion"]
        with self.assertRaises(ValueError):
            resolve_character_voices(self.story, self.catalog, self.selections)

    def test_duplicate_catalog_id_rejected(self):
        self.catalog[1]["id"] = "existing_voice_1"
        with self.assertRaises(ValueError):
            resolve_character_voices(self.story, self.catalog, self.selections)


if __name__ == "__main__":
    unittest.main()
