import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import quality


def _big_file() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    f.write(b"0" * 500_000)
    f.close()
    return f.name


NOMINAL = {
    "total_duration": 72.0,
    "n_blocks": 6,
    "blocks_with_image": 6,
    "n_cues": 48,
    "visuals_possible": True,
}


class TestScoreGeneration(unittest.TestCase):
    def test_nominal_run_scores_full(self):
        score, flags = quality.score_generation(NOMINAL, _big_file())
        self.assertEqual(score, 100)
        self.assertEqual(flags, [])

    def test_short_voiceover_penalised(self):
        score, flags = quality.score_generation({**NOMINAL, "total_duration": 42.0, "n_cues": 28}, _big_file())
        self.assertEqual(score, 70)  # -30
        self.assertTrue(any("moins de 60s" in f for f in flags))

    def test_missing_scene_visuals_penalised(self):
        score, flags = quality.score_generation({**NOMINAL, "blocks_with_image": 3}, _big_file())
        self.assertEqual(score, 80)  # -20
        self.assertTrue(any("sans visuel" in f for f in flags))

    def test_no_penalty_when_visuals_not_possible(self):
        score, flags = quality.score_generation(
            {**NOMINAL, "blocks_with_image": 0, "visuals_possible": False}, _big_file()
        )
        self.assertEqual(score, 100)
        self.assertEqual(flags, [])

    def test_caption_density_out_of_range_penalised(self):
        # 6 cues sur 72s -> 0.08 cue/s, sous le plancher
        score, flags = quality.score_generation({**NOMINAL, "n_cues": 6}, _big_file())
        self.assertEqual(score, 90)  # -10
        self.assertTrue(any("Densité de sous-titres" in f for f in flags))

    def test_tiny_final_file_penalised(self):
        tiny = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tiny.write(b"0" * 100)
        tiny.close()
        score, flags = quality.score_generation(NOMINAL, tiny.name)
        self.assertEqual(score, 60)  # -40
        self.assertTrue(any("anormalement petit" in f for f in flags))

    def test_missing_final_file_penalised(self):
        score, flags = quality.score_generation(NOMINAL, "/nope/does-not-exist.mp4")
        self.assertEqual(score, 60)

    def test_score_never_negative(self):
        score, _ = quality.score_generation(
            {"total_duration": 10.0, "n_blocks": 6, "blocks_with_image": 0,
             "n_cues": 2, "visuals_possible": True},
            "/nope.mp4",
        )
        self.assertGreaterEqual(score, 0)

    def test_pass_threshold_boundary(self):
        # -30 (court) => 70, pile au seuil -> passe
        score, _ = quality.score_generation({**NOMINAL, "total_duration": 40.0, "n_cues": 26}, _big_file())
        self.assertEqual(score, quality.PASS_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
