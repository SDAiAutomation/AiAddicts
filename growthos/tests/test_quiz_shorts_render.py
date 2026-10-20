"""Rendu réel (FFmpeg + libass) d'un mini-chapitre vertical avec audio synthétique : résolution, durée, nettoyage."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine import quiz_shorts
from engine.quiz import compile_quiz
from tests.test_quiz_chapters import script


def _has_libass() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return " subtitles " in out


@unittest.skipUnless(_has_libass(), "ffmpeg avec libass requis")
class VerticalRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = compile_quiz(script())
        self.plan = {"chapter": 1, "label": "EASY", "part": 1, "parts": 1, "file": "quiz_easy.mp4",
                     "first_question": 1, "last_question": 1, "blocks": [1, 2, 3]}  # card, question 1, reveal 1
        for index in self.plan["blocks"]:
            block = self.data["blocks"][index]
            path = quiz_shorts.audio_path(self.tmp, index + 1, block)
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=300:duration={7.0 if block['quiz_phase'] == 'question' else 1.6}",
                            "-c:a", "libmp3lame", str(path)], check=True, capture_output=True)

    def test_renders_a_validated_1080x1920_file_and_removes_temp_files(self):
        out = self.tmp / "shorts"
        result = quiz_shorts.render_plan(self.data, self.tmp, self.plan, out)
        self.assertEqual((result["width"], result["height"]), (1080, 1920))
        self.assertEqual(result["status"], "ready")
        self.assertAlmostEqual(result["duration"], 1.6 + 7.0 + 1.6, delta=0.2)
        self.assertEqual([p.name for p in out.iterdir()], ["quiz_easy.mp4"])  # no temp folder left behind
        self.assertTrue(quiz_shorts.probe(out / "quiz_easy.mp4")["has_audio"])

    def test_failed_render_publishes_nothing(self):
        quiz_shorts.audio_path(self.tmp, 3, self.data["blocks"][2]).unlink()
        out = self.tmp / "shorts"
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.render_plan(self.data, self.tmp, self.plan, out)
        self.assertEqual(list(out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
