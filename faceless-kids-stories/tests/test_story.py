import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.story import load_story, slugify  # noqa: E402

SAMPLE_STORY = {
    "title": "Le Petit Hibou Courageux",
    "theme": "courage",
    "voice_id": "abc123",
    "aspect_ratio": "9:16",
    "style_prompt": "3D animation style",
    "blocks": [
        {"vo": "Il était une fois...", "visual": "A small owl in a tree"},
        {"vo": "La suite de l'histoire.", "visual": "The owl flying at night"},
    ],
}


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Le Petit Hibou Courageux"), "le-petit-hibou-courageux")

    def test_accents_and_punctuation(self):
        self.assertEqual(slugify("Héllo, Wörld!!"), "héllo-wörld")

    def test_empty_falls_back(self):
        self.assertEqual(slugify("???"), "histoire")


class TestLoadStory(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(__file__).resolve().parent / "_tmp"
        self.tmp_dir.mkdir(exist_ok=True)

    def tearDown(self):
        for f in self.tmp_dir.glob("*.json"):
            f.unlink()
        self.tmp_dir.rmdir()

    def _write(self, data) -> Path:
        path = self.tmp_dir / "story.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_valid_story_loads(self):
        path = self._write(SAMPLE_STORY)
        story = load_story(path)
        self.assertEqual(story.title, "Le Petit Hibou Courageux")
        self.assertEqual(len(story.blocks), 2)
        self.assertEqual(story.blocks[0].index, 0)
        self.assertEqual(story.slug, "le-petit-hibou-courageux")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_story(self.tmp_dir / "does-not-exist.json")

    def test_missing_top_level_field_raises(self):
        data = dict(SAMPLE_STORY)
        del data["voice_id"]
        path = self._write(data)
        with self.assertRaises(ValueError):
            load_story(path)

    def test_invalid_aspect_ratio_raises(self):
        data = dict(SAMPLE_STORY)
        data["aspect_ratio"] = "4:3"
        path = self._write(data)
        with self.assertRaises(ValueError):
            load_story(path)

    def test_empty_blocks_raises(self):
        data = dict(SAMPLE_STORY)
        data["blocks"] = []
        path = self._write(data)
        with self.assertRaises(ValueError):
            load_story(path)

    def test_block_missing_field_raises(self):
        data = dict(SAMPLE_STORY)
        data["blocks"] = [{"vo": "texte sans visuel"}]
        path = self._write(data)
        with self.assertRaises(ValueError):
            load_story(path)


if __name__ == "__main__":
    unittest.main()
