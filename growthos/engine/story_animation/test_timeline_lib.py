import math
import unittest

from growthos.engine.story_animation import lipsync, quality, subtitles, timeline


def alignment(text: str, per_char: float = 0.1, start: float = 0.0) -> dict:
    return {
        "characters": list(text),
        "character_start_times_seconds": [round(start + i * per_char, 4) for i in range(len(text))],
        "character_end_times_seconds": [round(start + (i + 1) * per_char, 4) for i in range(len(text))],
    }


def loud(n: int) -> list:
    return [1.0] * n


class LipsyncTests(unittest.TestCase):
    def test_vowels_round_and_closed_consonants(self):
        al = alignment("aoba", per_char=0.3)  # three frames per sound at 10 fps
        self.assertEqual(lipsync.mouth_classes(loud(12), al, fps=10), "ooorrrcccooo")

    def test_silence_closes_the_mouth(self):
        al = alignment("aaaa")
        env = [1.0, 1.0, 0.01, 0.01, 0.01, 0.01, 1.0, 1.0]
        classes = lipsync.mouth_classes(env, al, fps=10)
        self.assertEqual(classes[2:6], "cccc")

    def test_frames_after_the_text_are_closed(self):
        classes = lipsync.mouth_classes(loud(30), alignment("aa"), fps=10)
        self.assertEqual(classes[3:], "c" * 27)

    def test_single_frame_glitch_is_smoothed(self):
        al = {"characters": list("aaabaaa"), "character_start_times_seconds": [i * 0.1 for i in range(7)],
              "character_end_times_seconds": [(i + 1) * 0.1 for i in range(7)]}
        self.assertEqual(lipsync.mouth_classes(loud(7), al, fps=10), "ooooooo")

    def test_accents_open_and_round(self):
        self.assertEqual(lipsync.mouth_classes(loud(2), alignment("éô"), fps=10), "or")

    def test_bad_alignment_is_rejected(self):
        with self.assertRaises(ValueError):
            lipsync.mouth_classes([1.0], {"characters": ["a"], "character_start_times_seconds": [], "character_end_times_seconds": []}, fps=10)
        with self.assertRaises(ValueError):
            lipsync.mouth_classes([1.0], {"characters": ["a", "b"], "character_start_times_seconds": [0.2, 0.1], "character_end_times_seconds": [0.3, 0.2]}, fps=10)

    def test_envelope_and_normalisation(self):
        samples = [0.0] * 100 + [1000.0] * 100
        env = lipsync.rms_envelope(samples, sample_rate=100, fps=1)
        self.assertEqual(len(env), 2)
        self.assertEqual(env[0], 0.0)
        norm = lipsync.normalise(env)
        self.assertAlmostEqual(max(norm), 1.0, places=3)
        self.assertEqual(lipsync.normalise([]), [])
        self.assertEqual(lipsync.normalise([0.0, 0.0, 0.0]), [0.0, 0.0, 0.0])
        with self.assertRaises(ValueError):
            lipsync.rms_envelope([1.0], 0, 24)


class SubtitleTests(unittest.TestCase):
    def test_words_and_offset(self):
        words = subtitles.words_from_alignment(alignment("ab cd", per_char=0.1), offset=2.0)
        self.assertEqual([w[0] for w in words], ["ab", "cd"])
        self.assertAlmostEqual(words[0][1], 2.0)
        self.assertAlmostEqual(words[1][2], 2.5)

    def test_groups_of_three_and_punctuation_breaks(self):
        words = [("Alors", 0, .2), ("pourquoi", .3, .6), ("il", .7, .8), ("me", .9, 1.0), ("suit", 1.1, 1.3), ("partout", 1.4, 1.8), ("?", 1.8, 1.9)]
        chunks = subtitles.chunk_words(words)
        self.assertEqual([c["text"] for c in chunks], ["Alors pourquoi il", "me suit partout ?"])

    def test_sentence_end_closes_a_group(self):
        words = [("Moi", 0, .2), ("?", .2, .3), ("Jamais", .5, .8)]
        self.assertEqual([c["text"] for c in subtitles.chunk_words(words)], ["Moi ?", "Jamais"])

    def test_no_overlap_and_positive_length(self):
        chunks = [{"text": "a", "start": 0.0, "end": 1.0}, {"text": "b", "start": 0.5, "end": 0.6}, {"text": "c", "start": 0.55, "end": 0.5}]
        fixed = subtitles.remove_overlaps(chunks)
        for a, b in zip(fixed, fixed[1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-9)
        for c in fixed:
            self.assertGreater(c["end"], c["start"])

    def test_bad_alignment_rejected(self):
        with self.assertRaises(ValueError):
            subtitles.words_from_alignment({"characters": ["a"], "character_start_times_seconds": [0.0], "character_end_times_seconds": []})


def two_lines():
    return [
        {"who": "ros", "text": "Bonjour Pip", "duration_s": 1.1, "alignment": alignment("Bonjour Pip", 0.1), "envelope": loud(26)},
        {"who": "pip", "text": "Madame !", "duration_s": 0.8, "alignment": alignment("Madame !", 0.1), "envelope": loud(19)},
    ]


class TimelineTests(unittest.TestCase):
    def test_start_end_and_total_follow_measured_durations(self):
        tl = timeline.build_timeline(two_lines(), fps=24)
        a, b = tl["lines"]
        self.assertEqual((a["start"], a["end"]), (0.5, 1.6))
        self.assertAlmostEqual(b["start"], 1.95)
        self.assertAlmostEqual(tl["total"], 2.75 + timeline.TAIL_S, places=3)

    def test_cuts_sit_in_the_pauses(self):
        tl = timeline.build_timeline(two_lines(), fps=24)
        cuts = timeline.shot_cuts(tl)
        self.assertEqual(cuts[0], 0.0)
        self.assertAlmostEqual(cuts[1], (1.6 + 1.95) / 2, places=3)
        self.assertEqual(cuts[-1], tl["total"])
        self.assertEqual(cuts, sorted(cuts))

    def test_extra_cut_must_follow_the_last_cut(self):
        tl = timeline.build_timeline(two_lines())
        self.assertEqual(len(timeline.shot_cuts(tl, extra_cuts=(3.0,))), 4)
        with self.assertRaises(ValueError):
            timeline.shot_cuts(tl, extra_cuts=(0.5,))
        with self.assertRaises(ValueError):
            timeline.shot_cuts(tl, extra_cuts=(tl["total"] + 1,))

    def test_active_line_and_mouth_lookup(self):
        tl = timeline.build_timeline(two_lines(), fps=24)
        self.assertEqual(timeline.active_line(tl, 0.2), -1)
        self.assertEqual(timeline.active_line(tl, 1.0), 0)
        self.assertEqual(timeline.active_line(tl, 2.2), 1)
        self.assertEqual(timeline.mouth_at(tl, "pip", 0), "c")
        self.assertEqual(timeline.mouth_at(tl, "ros", 24), "r")  # 0.5 s into "Bonjour" the sound is the "u"
        self.assertEqual(timeline.mouth_at(tl, "pip", 30), "c")

    def test_subtitles_are_inside_the_clip_and_ordered(self):
        tl = timeline.build_timeline(two_lines())
        for s in tl["subs"]:
            self.assertGreaterEqual(s["start"], 0.0)
            self.assertLess(s["end"], tl["total"])
        self.assertEqual(tl["subs"], sorted(tl["subs"], key=lambda s: s["start"]))

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError):
            timeline.build_timeline([])
        for bad in (0, -1, True, float("nan"), float("inf"), "1"):
            lines = two_lines()
            lines[0]["duration_s"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                timeline.build_timeline(lines)
        with self.assertRaises(ValueError):
            timeline.build_timeline(two_lines(), fps=0)

    def test_sixty_second_limit(self):
        lines = two_lines()
        lines[0]["duration_s"] = 58.0
        with self.assertRaises(ValueError):
            timeline.build_timeline(lines)


GOOD = {"video_duration_s": 21.6, "audio_duration_s": 21.58, "width": 1080, "height": 1920, "fps": 24.0, "size_bytes": 8_000_000,
        "black": [(0.0, 0.5), (21.0, 21.6)], "freeze": [], "mean_volume_db": -19.4, "max_volume_db": -0.8}
EXPECTED = {"width": 1080, "height": 1920, "fps": 24}


class QualityTests(unittest.TestCase):
    def test_good_clip_passes_and_fades_are_allowed(self):
        self.assertEqual(quality.check_media(GOOD, EXPECTED), [])

    def test_each_defect_is_reported(self):
        cases = {
            "audio_duration_s": (19.0, "differ"), "width": (540, "resolution"), "fps": (30.0, "frame rate"),
            "size_bytes": (50 * 1048576, "limit"), "max_volume_db": (0.0, "clipping"), "mean_volume_db": (-50.0, "silent"),
            "black": ([(5.0, 5.5)], "black"), "freeze": ([(8.0, 9.5)], "frozen"),
        }
        for key, (value, word) in cases.items():
            with self.subTest(key):
                problems = quality.check_media({**GOOD, key: value}, EXPECTED)
                self.assertTrue(any(word in p for p in problems), problems)

    def test_short_black_or_freeze_is_tolerated(self):
        self.assertEqual(quality.check_media({**GOOD, "black": [(5.0, 5.1)], "freeze": [(8.0, 8.5)]}, EXPECTED), [])

    def test_missing_or_bad_measurements_fail(self):
        for key in ("video_duration_s", "width", "size_bytes"):
            bad = {k: v for k, v in GOOD.items() if k != key}
            self.assertTrue(quality.check_media(bad, EXPECTED))
        self.assertTrue(quality.check_media({**GOOD, "fps": float("nan")}, EXPECTED))
        self.assertTrue(quality.check_media({**GOOD, "width": True}, EXPECTED))

    def test_ffmpeg_text_parsers(self):
        black = "[blackdetect @ 0x1] black_start:0 black_end:0.5 black_duration:0.5\n[blackdetect @ 0x1] black_start:21.1 black_end:21.6 black_duration:0.5"
        self.assertEqual(quality.parse_blackdetect(black), [(0.0, 0.5), (21.1, 21.6)])
        freeze = "lavfi.freezedetect.freeze_start: 8.0\nlavfi.freezedetect.freeze_duration: 1.5\nlavfi.freezedetect.freeze_end: 9.5\nfreeze_start: 12.0"
        self.assertEqual(quality.parse_freezedetect(freeze), [(8.0, 9.5)])
        self.assertEqual(quality.parse_blackdetect(""), [])


if __name__ == "__main__":
    unittest.main()
