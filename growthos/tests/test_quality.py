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
    "total_duration": 35.0, "content_goal": "reach", "n_blocks": 6,
    "n_shots": 12, "max_shot_duration": 3.0, "hook_duration": 2.8,
    "blocks_with_image": 6, "n_cues": 35, "visuals_possible": True,
    "editorial": {"score": 90, "issues": []},
}


class TestScoreGeneration(unittest.TestCase):
    def test_nominal_run_scores_full(self):
        self.assertEqual(quality.score_generation(NOMINAL, _big_file()), (100, []))

    def test_short_monetization_video_is_penalised(self):
        metrics = {**NOMINAL, "content_goal": "monetization", "total_duration": 42.0, "n_cues": 28}
        score, flags = quality.score_generation(metrics, _big_file())
        self.assertEqual(score, 70)
        self.assertTrue(any("moins de 60s" in f for f in flags))

    def test_long_reach_video_is_penalised(self):
        score, flags = quality.score_generation({**NOMINAL, "total_duration": 80.0, "n_cues": 80}, _big_file())
        self.assertEqual(score, 85)
        self.assertTrue(any("objectif de portée" in f for f in flags))

    def test_slow_hook_and_shot_are_penalised(self):
        score, flags = quality.score_generation(
            {**NOMINAL, "hook_duration": 6.0, "max_shot_duration": 8.0}, _big_file()
        )
        self.assertEqual(score, 70)
        self.assertTrue(any("Hook" in f for f in flags))
        self.assertTrue(any("Plan visuel" in f for f in flags))

    def test_weak_editorial_score_is_penalised(self):
        score, flags = quality.score_generation(
            {**NOMINAL, "editorial": {"score": 55, "issues": ["Hook générique."]}}, _big_file()
        )
        self.assertEqual(score, 65)
        self.assertTrue(any("éditoriale" in f for f in flags))

    def test_generic_hook_score_is_not_accepted_as_publish_ready(self):
        score, _ = quality.score_generation(
            {**NOMINAL, "editorial": {"score": 80, "issues": ["Ouverture générique."]}},
            _big_file(),
        )
        self.assertEqual(score, 65)

    def test_missing_scene_visuals_penalised(self):
        score, flags = quality.score_generation({**NOMINAL, "blocks_with_image": 3}, _big_file())
        self.assertEqual(score, 80)
        self.assertTrue(any("sans visuel" in f for f in flags))

    def test_no_penalty_when_visuals_not_possible(self):
        metrics = {**NOMINAL, "blocks_with_image": 0, "visuals_possible": False}
        self.assertEqual(quality.score_generation(metrics, _big_file()), (100, []))

    def test_caption_density_out_of_range_penalised(self):
        score, flags = quality.score_generation({**NOMINAL, "n_cues": 2}, _big_file())
        self.assertEqual(score, 90)
        self.assertTrue(any("Densité de sous-titres" in f for f in flags))

    def test_caption_density_too_high_penalised(self):
        score, flags = quality.score_generation({**NOMINAL, "n_cues": 70}, _big_file())
        self.assertEqual(score, 90)
        self.assertTrue(any("Densité de sous-titres" in f for f in flags))

    def test_tiny_final_file_penalised(self):
        tiny = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tiny.write(b"0" * 100)
        tiny.close()
        score, flags = quality.score_generation(NOMINAL, tiny.name)
        self.assertEqual(score, 60)
        self.assertTrue(any("anormalement petit" in f for f in flags))

    def test_score_never_negative(self):
        metrics = {**NOMINAL, "total_duration": 2, "hook_duration": 10,
                   "max_shot_duration": 10, "blocks_with_image": 0, "n_cues": 100,
                   "editorial": {"score": 0, "issues": []}}
        score, _ = quality.score_generation(metrics, "/nope.mp4")
        self.assertGreaterEqual(score, 0)


if __name__ == "__main__":
    unittest.main()
