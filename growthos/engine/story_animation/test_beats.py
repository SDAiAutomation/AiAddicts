import unittest

from growthos.engine.story_animation import beats
from growthos.engine.story_animation.test_timeline_lib import alignment

LONG = ("Un matin, la file s'allongeait devant la porte, et personne ne savait pourquoi. "
        "Quelqu'un a sorti son téléphone. Puis tout le monde reculait, lentement, sans un mot.")


def line(text, start=0.5, per_char=0.06, speaker="narrator", aligned=True):
    return {"text": text, "start": start, "dur": len(text) * per_char, "speaker_id": speaker, "shot_index": 0,
            "alignment": alignment(text, per_char) if aligned else None}


class SplitLine(unittest.TestCase):
    def test_short_line_stays_one_beat(self):
        text = "Pourquoi cette file ?"
        out = beats.split_line(text, alignment(text, 0.1), 2.1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], text)

    def test_long_line_cut_at_clauses_into_2_to_4_s(self):
        al = alignment(LONG, 0.06)
        out = beats.split_line(LONG, al, len(LONG) * 0.06)
        self.assertGreaterEqual(len(out), 3)
        for b in out:
            self.assertLessEqual(b["end"] - b["start"], beats.MAX_BEAT_S + 1.0, b)
        # every beat but possibly the last is at least the minimum
        for b in out[:-1]:
            self.assertGreaterEqual(b["end"] - b["start"], beats.MIN_BEAT_S - 0.3, b)
        # the beats cover the text in order, without losing a word
        self.assertEqual(" ".join(b["text"] for b in out).split(), LONG.split())
        self.assertTrue(any(b["text"].startswith("Quelqu'un") for b in out))

    def test_never_splits_a_word(self):
        text = " ".join(["anticonstitutionnellement"] * 12)   # one clause, no punctuation, ~18 s
        out = beats.split_line(text, alignment(text, 0.06), len(text) * 0.06)
        self.assertGreater(len(out), 1)
        for b in out:
            for word in b["text"].split():
                self.assertEqual(word, "anticonstitutionnellement")

    def test_proportional_timing_when_alignment_does_not_match(self):
        bad = alignment("autre texte", 0.1)
        out = beats.split_line(LONG, bad, 10.0)
        self.assertAlmostEqual(out[0]["start"], 0.0, places=2)
        self.assertAlmostEqual(out[-1]["end"], 10.0, places=1)
        self.assertEqual(beats.split_line(LONG, None, 10.0)[-1]["end"], out[-1]["end"])

    def test_measured_alignment_drives_the_cut_times(self):
        al = alignment(LONG, 0.06)
        al["character_start_times_seconds"] = [t * 2 for t in al["character_start_times_seconds"]]
        al["character_end_times_seconds"] = [t * 2 for t in al["character_end_times_seconds"]]
        slow = beats.split_line(LONG, al, len(LONG) * 0.12)
        fast = beats.split_line(LONG, alignment(LONG, 0.06), len(LONG) * 0.06)
        self.assertGreater(slow[-1]["end"], fast[-1]["end"] * 1.9)


class BuildAndCap(unittest.TestCase):
    def test_absolute_times_and_line_metadata(self):
        lines = [line(LONG, start=0.5), line("Et alors ?", start=0.5 + len(LONG) * 0.06 + 0.35, speaker="pip")]
        bs = beats.build_beats(lines)
        self.assertEqual([b["index"] for b in bs], list(range(len(bs))))
        self.assertEqual(bs[-1]["speaker_id"], "pip")
        self.assertTrue(bs[-1]["line_first"])
        self.assertGreaterEqual(bs[0]["start"], 0.5)
        for a, b in zip(bs, bs[1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-6)

    def test_merge_to_cap_prefers_same_line(self):
        lines = [line(LONG, start=0.5), line("Et alors ?", start=20.0, speaker="pip")]
        bs = beats.build_beats(lines)
        capped = beats.merge_to_cap(bs, len(bs) - 1)
        self.assertEqual(len(capped), len(bs) - 1)
        self.assertEqual(capped[-1]["text"], "Et alors ?")
        self.assertEqual(beats.merge_to_cap(bs, 1)[0]["end"], bs[-1]["end"])
        with self.assertRaises(ValueError):
            beats.merge_to_cap(bs, 0)

    def test_segments_cover_the_whole_video(self):
        l1 = line(LONG, start=0.5)
        l2 = line("Et alors ?", start=l1["start"] + l1["dur"] + 0.35, speaker="pip")
        total = l2["start"] + l2["dur"] + 2.6
        bs = beats.build_beats([l1, l2])
        spans = beats.segments(bs, [l1, l2], total)
        self.assertEqual(len(spans), len(bs))
        self.assertEqual(spans[0][0], 0.0)
        self.assertAlmostEqual(spans[-1][1], total, places=3)
        for (a, b), (c, _) in zip(spans, spans[1:]):
            self.assertEqual(b, c)
            self.assertGreaterEqual(b - a, beats.MIN_SEGMENT_S - 1e-6)
        # the cut between the two lines falls inside the pause
        k = next(i for i, b in enumerate(bs) if b["line_index"] == 1)
        self.assertTrue(l1["start"] + l1["dur"] <= spans[k][0] <= l2["start"])


if __name__ == "__main__":
    unittest.main()
