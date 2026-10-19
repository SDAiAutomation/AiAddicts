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


class ThumbnailVariantTests(unittest.TestCase):
    STUDIO = _QUIZ_THEME_COLOURS["studio"]

    def test_three_variants_pass_every_automatic_check(self):
        for theme, colours in _QUIZ_THEME_COLOURS.items():
            for variant in thumbnail.VARIANTS:
                with tempfile.TemporaryDirectory() as folder:
                    image, report = thumbnail.render_variant("Chemistry", 25, colours, "en", variant, f"{folder}/t.jpg")
                    self.assertEqual(image.size, (1280, 720), (theme, variant))
                    self.assertEqual(report["issues"], [], (theme, variant, report))
                    self.assertLess(report["bytes"], 2 * 1024 * 1024)
                    self.assertGreaterEqual(report["minFontPxAt168"], thumbnail.MIN_FONT_AT_168)
                    self.assertTrue(report["safeZoneClear"])

    def test_variants_are_distinct_and_the_count_is_always_the_real_one(self):
        images = {v: thumbnail.render_variant("Chemistry", 25, self.STUDIO, "en", v)[0].tobytes() for v in thumbnail.VARIANTS}
        self.assertEqual(len(set(images.values())), 3)
        for variant in thumbnail.VARIANTS:
            self.assertEqual(thumbnail.render_variant("Chemistry", 17, self.STUDIO, "en", variant)[1]["questionCount"], 17)

    def test_a_promise_in_the_topic_is_never_displayed(self):
        for topic in ("Why 99% fail this quiz", "The impossible quiz", "Garanti sans faute"):
            _, report = thumbnail.render_variant(topic, 25, self.STUDIO, "en")
            self.assertIn("topic_claim_removed", report["issues"], topic)
        self.assertTrue(thumbnail.has_claim("Only 1 in 100 can pass"))
        self.assertFalse(thumbnail.has_claim("Chimie : les éléments"))

    def test_long_topics_are_shortened_on_a_whole_word_never_on_a_connector(self):
        topic = "Histoire de la Rome antique et de ses empereurs et de leurs batailles les plus célèbres"
        _, report = thumbnail.render_variant(topic, 25, self.STUDIO, "fr")
        self.assertTrue(report["topicShortened"])
        self.assertGreaterEqual(report["minFontPxAt168"], thumbnail.MIN_FONT_AT_168)

    def test_unknown_variant_is_refused(self):
        with self.assertRaises(ValueError):
            thumbnail.render_variant("Chemistry", 25, self.STUDIO, "en", "Z")

    def test_script_builds_all_variants_and_only_for_long_quizzes(self):
        script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
        script["quiz"]["recipe"] = "long"
        with tempfile.TemporaryDirectory() as folder:
            built = thumbnail.build_variants_for_script(script, folder)
            self.assertEqual(list(built), ["A", "B", "C"])
            self.assertEqual({info["axis"] for info in built.values()}, {"topic", "number", "text"})
            for info in built.values():
                self.assertTrue(Path(info["path"]).exists())
        script["quiz"]["recipe"] = "quick"
        with self.assertRaises(ValueError):
            thumbnail.build_variants_for_script(script, "/tmp/never")


class PublishThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
        self.script["quiz"]["recipe"] = "long"

    def test_variants_are_uploaded_and_recorded_in_the_script(self):
        from unittest import mock
        from engine import assembler
        uploads = []

        def fake_upload(_client, item_id, path, variant="A"):
            uploads.append((variant, Path(path).name))
            return f"https://storage/{item_id}.thumbnail{'' if variant == 'A' else '-' + variant.lower()}.jpg"

        with tempfile.TemporaryDirectory() as folder, mock.patch.object(assembler.storage, "upload_thumbnail", fake_upload):
            assembler._publish_thumbnail(object(), "item", self.script, Path(folder))
        self.assertEqual([u[0] for u in uploads], ["A", "B", "C"])
        self.assertEqual(self.script["thumbnail_url"], "https://storage/item.thumbnail.jpg")
        self.assertEqual([v["id"] for v in self.script["thumbnail_variants"]], ["A", "B", "C"])
        self.assertEqual(self.script["thumbnail_variants"][1]["url"], "https://storage/item.thumbnail-b.jpg")

    def test_an_upload_failure_never_raises_and_leaves_no_partial_urls(self):
        from unittest import mock
        from engine import assembler
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(assembler.storage, "upload_thumbnail", side_effect=RuntimeError("down")):
            assembler._publish_thumbnail(object(), "item", self.script, Path(folder))
        self.assertNotIn("thumbnail_url", self.script)
        self.assertNotIn("thumbnail_variants", self.script)

    def test_short_quizzes_get_nothing(self):
        from engine import assembler
        self.script["quiz"]["recipe"] = "quick"
        assembler._publish_thumbnail(object(), "item", self.script, Path("/tmp"))
        self.assertNotIn("thumbnail_url", self.script)


if __name__ == "__main__":
    unittest.main()
