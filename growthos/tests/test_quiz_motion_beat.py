import re
import unittest

from engine.quiz_motion import REVEAL_BEAT_SECONDS, scene_events


def _ends(events):
    # ASS "Dialogue: layer,start,end,style,..." -> fin (secondes) des événements du chiffre du minuteur.
    out = []
    for line in events:
        if ",QuizTimer," in line:
            h, m, sec = re.match(r"Dialogue: \d+,[^,]+,(\d+):(\d+):([\d.]+),", line).groups()
            out.append(int(h) * 3600 + int(m) * 60 + float(sec))
    return out


def _block(beat):
    return {"quiz_phase": "question", "quiz_presentation": "motion", "quiz_theme": "studio",
            "quiz_question_number": 1, "quiz_question_total": 3, "quiz_question": "Q ?",
            "quiz_choices": ["a", "b", "c", "d"], "hold_after_seconds": 5, "quiz_reveal_beat_seconds": beat}


class RevealBeatTests(unittest.TestCase):
    def test_timer_stops_before_the_end_of_the_block(self):
        for size in ((1920, 1080), (1080, 1920)):
            with self.subTest(size=size):
                events = scene_events(_block(0.5), 0, 12, *size)
                ends = _ends(events)
                self.assertTrue(ends)
                self.assertLessEqual(max(ends), 11.5 + 0.01)

    def test_without_beat_timer_runs_to_the_end(self):
        events = scene_events(_block(0), 0, 12, 1920, 1080)
        self.assertAlmostEqual(max(_ends(events)), 12, delta=0.01)

    def test_beat_value(self):
        self.assertEqual(REVEAL_BEAT_SECONDS, 0.5)
