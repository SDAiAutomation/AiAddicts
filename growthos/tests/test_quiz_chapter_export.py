import unittest

from engine.quiz_chapter_export import chapter_segments


class QuizChapterExportTests(unittest.TestCase):
    def scenes(self):
        result = []
        t = 0.0
        for n in range(1, 51):
            for phase in ("question", "reveal"):
                result.append({"phase": phase, "question_number": n, "start": t, "end": t + 3.0})
                t += 3.0
        return result

    def test_five_measured_chapters(self):
        chapters = chapter_segments(self.scenes())
        self.assertEqual([c["label"] for c in chapters], ["EASY", "MEDIUM", "HARD", "EXPERT", "GENIUS"])
        self.assertEqual([(c["start"], c["end"]) for c in chapters],
                         [(0.0, 60.0), (60.0, 120.0), (120.0, 180.0),
                          (180.0, 240.0), (240.0, 300.0)])
        self.assertEqual(chapters[-1]["last_question"], 50)

    def test_rejects_incomplete_or_wrong_order(self):
        with self.assertRaises(ValueError):
            chapter_segments(self.scenes()[:-1])
        bad = self.scenes()
        bad[2]["question_number"] = 3
        with self.assertRaises(ValueError):
            chapter_segments(bad)

    def test_rejects_timecode_gap(self):
        bad = self.scenes()
        bad[10]["start"] += 1
        with self.assertRaises(ValueError):
            chapter_segments(bad)


if __name__ == "__main__":
    unittest.main()
