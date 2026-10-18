import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from engine import thumbnail
from engine.captions import _QUIZ_THEME_COLOURS
from engine.quiz import compile_quiz


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))

    def test_only_long_quizzes_get_a_thumbnail(self):
        self.assertFalse(thumbnail.is_long_quiz(self.script))
        with self.assertRaises(ValueError):
            thumbnail.build_for_script(self.script, "/tmp/never.jpg")
        self.script["quiz"]["recipe"] = "long"
        self.assertTrue(thumbnail.is_long_quiz(self.script))

    def test_thumbnail_matches_youtube_requirements(self):
        self.script["quiz"]["recipe"] = "long"
        with tempfile.TemporaryDirectory() as folder:
            out = thumbnail.build_for_script(self.script, f"{folder}/thumb.jpg")
            image = Image.open(out)
            self.assertEqual(image.size, (1280, 720))
            self.assertEqual(image.format, "JPEG")
            self.assertLess(Path(out).stat().st_size, 2 * 1024 * 1024)

    def test_long_titles_and_every_theme_render_without_error(self):
        topic = "Histoire de la Rome antique, de ses empereurs et de leurs batailles les plus célèbres"
        for colours in _QUIZ_THEME_COLOURS.values():
            image = thumbnail.render_thumbnail(topic, 25, colours, "fr")
            self.assertEqual(image.size, (1280, 720))

    def test_bottom_right_corner_stays_empty_for_the_duration_badge(self):
        image = thumbnail.render_thumbnail("Chemistry", 25, _QUIZ_THEME_COLOURS["studio"], "en")
        corner = image.crop((1100, 640, 1280, 720))
        self.assertLess(len({corner.getpixel((x, y))[0] // 24 for x in range(0, 180, 6) for y in range(0, 80, 6)}), 4)


if __name__ == "__main__":
    unittest.main()
