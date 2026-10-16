import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.explainer import render, voiceover  # noqa: E402


class TestPlanTempo(unittest.TestCase):
    def test_line_that_fits_is_left_alone(self):
        lines = [{"start": 0.0, "duration": 2.0}, {"start": 4.0, "duration": 1.0}]
        voiceover.plan_tempo(lines, 10.0)
        self.assertEqual([l["tempo"] for l in lines], [1.0, 1.0])
        self.assertEqual([l["overflow"] for l in lines], [0.0, 0.0])

    def test_slightly_long_line_is_sped_up_to_fit(self):
        lines = [{"start": 0.0, "duration": 2.0}, {"start": 2.0, "duration": 1.0}]
        voiceover.plan_tempo(lines, 10.0)
        self.assertGreater(lines[0]["tempo"], 1.0)
        self.assertLessEqual(lines[0]["tempo"], voiceover.MAX_TEMPO)

    def test_very_long_line_reports_overflow_instead_of_distorting(self):
        lines = [{"start": 0.0, "duration": 6.0}, {"start": 2.0, "duration": 1.0}]
        voiceover.plan_tempo(lines, 10.0)
        self.assertEqual(lines[0]["tempo"], voiceover.MAX_TEMPO)
        self.assertGreater(lines[0]["overflow"], 0)

    def test_last_line_is_bounded_by_total_duration(self):
        lines = [{"start": 9.0, "duration": 3.0}]
        voiceover.plan_tempo(lines, 10.0)
        self.assertGreater(lines[0]["overflow"], 0)

    def test_cache_key_depends_on_text_and_voice(self):
        self.assertNotEqual(voiceover._line_key("a", "v1"), voiceover._line_key("b", "v1"))
        self.assertNotEqual(voiceover._line_key("a", "v1"), voiceover._line_key("a", "v2"))
        self.assertEqual(voiceover._line_key("a", "v1"), voiceover._line_key("a", "v1"))


class TestAudioArgs(unittest.TestCase):
    def test_without_voice_the_sfx_track_is_unchanged(self):
        self.assertEqual(render.audio_args(None), [])
        self.assertEqual(render.voice_inputs(None), [])

    def test_with_voice_sfx_are_ducked_under_it(self):
        graph = " ".join(render.audio_args("voice.wav"))
        self.assertIn("sidechaincompress", graph)
        self.assertEqual(render.voice_inputs("voice.wav"), ["-i", "voice.wav"])


if __name__ == "__main__":
    unittest.main()
