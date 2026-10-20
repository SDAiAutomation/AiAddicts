import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from engine import quiz_backdrop, quiz_motion
from engine.quiz import normalize_quiz


def _script(**quiz):
    root = Path(__file__).resolve().parents[1]
    script = json.loads((root / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    script["quiz"].update({"recipe": "long", "presentation": "motion", **quiz})
    return script


def _fake_photo(prompt, out_path, aspect="16:9", **_kwargs):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Image.effect_mandelbrot((320, 200), (-2.2, -1.2, 1.0, 1.2), 40).convert("RGB").save(out_path, "JPEG")
    return out_path


class BackdropTests(unittest.TestCase):
    def test_backdrops_are_opt_in_and_only_for_long_motion_quizzes(self):
        self.assertFalse(quiz_backdrop.enabled(_script()))
        self.assertTrue(quiz_backdrop.enabled(_script(backdrops=True)))
        self.assertFalse(quiz_backdrop.enabled(_script(backdrops=True, presentation="classic")))
        self.assertFalse(quiz_backdrop.enabled(_script(backdrops=True, recipe="quick")))
        self.assertFalse(quiz_backdrop.enabled({"content_format": "standard", "quiz": {"backdrops": True}}))

    def test_contract_defaults_to_false_and_rejects_non_booleans(self):
        self.assertIs(normalize_quiz({"questions": []})["backdrops"], False)
        self.assertIs(normalize_quiz({"backdrops": True, "questions": []})["backdrops"], True)
        with self.assertRaisesRegex(ValueError, "backdrops"):
            normalize_quiz({"backdrops": "oui", "questions": []})

    def test_duotone_keeps_the_text_readable_whatever_the_picture(self):
        for theme, light in (("studio", False), ("minimal", True)):
            for part in range(quiz_motion.PARTS):
                stage = quiz_motion.stage_background(theme, part)
                with tempfile.TemporaryDirectory() as folder:
                    raw = _fake_photo("x", f"{folder}/raw.jpg")
                    out = quiz_backdrop.duotone(raw, f"{folder}/out.jpg", stage, light)
                    image = Image.open(out).convert("RGB")
                    self.assertEqual(image.size, (1920, 1080))
                    ink = (255, 255, 255) if not light else (17, 24, 39)
                    def lum(c):
                        chans = [v / 255 for v in c]
                        lin = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in chans]
                        return .2126 * lin[0] + .7152 * lin[1] + .0722 * lin[2]
                    brightest, darkest = image.getextrema(), None
                    extremes = [tuple(band[i] for band in brightest) for i in (0, 1)]
                    worst = max(extremes, key=lambda c: lum(c)) if not light else min(extremes, key=lambda c: lum(c))
                    high, low = sorted((lum(ink), lum(worst)), reverse=True)
                    self.assertGreaterEqual((high + .05) / (low + .05), 4.5, (theme, part, worst))

    def test_generate_returns_one_background_per_part_and_reuses_the_cache(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(quiz_backdrop.openai_images, "generate_image", side_effect=_fake_photo) as gen:
            first = quiz_backdrop.generate(_script(backdrops=True), Path(folder))
            self.assertEqual(len(first), quiz_motion.PARTS)
            self.assertTrue(all(first) and all(Path(p).exists() for p in first))
            self.assertEqual(gen.call_count, quiz_motion.PARTS)
            self.assertEqual(gen.call_args.kwargs.get("quality"), "low")
            self.assertEqual(quiz_backdrop.generate(_script(backdrops=True), Path(folder)), first)
            self.assertEqual(gen.call_count, quiz_motion.PARTS)  # rien de regénéré

    def test_a_failed_generation_leaves_the_plain_background(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(quiz_backdrop.openai_images, "generate_image", return_value=None):
            self.assertEqual(quiz_backdrop.generate(_script(backdrops=True), Path(folder)), [None] * quiz_motion.PARTS)

    def test_prompts_name_the_topic_and_forbid_text_and_people(self):
        prompt = quiz_backdrop._PROMPT.format(topic="chemistry", variant=quiz_backdrop._VARIANTS[0])
        self.assertIn("chemistry", prompt)
        for banned in ("No text", "no people", "no logos"):
            self.assertIn(banned.lower(), prompt.lower())
        # Quatre variantes pour le mode historique, une cinquième réservée au mode cinq niveaux.
        self.assertEqual(len(quiz_backdrop._VARIANTS), quiz_motion.FIVE_LEVEL_PARTS)
        self.assertGreaterEqual(len(quiz_backdrop._VARIANTS), quiz_motion.PARTS)
        self.assertEqual(len(set(quiz_backdrop._VARIANTS)), len(quiz_backdrop._VARIANTS))


if __name__ == "__main__":
    unittest.main()
