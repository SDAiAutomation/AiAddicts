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

    def test_editorial_flag_lists_every_issue_not_only_the_first(self):
        # Au benchmark du 2026-10-04 le drapeau n'affichait que la 1re raison
        # alors que le score de 70 venait de trois règles (accroche, titre, CTA).
        _, flags = quality.score_generation(
            {**NOMINAL, "editorial": {"score": 70, "issues": ["Hook plat.", "Titre trop long.", "CTA trop long."]}},
            _big_file(),
        )
        flag = next(f for f in flags if "éditoriale" in f)
        for reason in ("Hook plat.", "Titre trop long.", "CTA trop long."):
            self.assertIn(reason, flag)

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

    def test_no_shot_planning_key_is_backward_compatible(self):
        # Toutes les vidéos générées avant Phase 1 : la clé n'existe même pas.
        self.assertEqual(quality.score_generation(NOMINAL, _big_file()), (100, []))

    def test_unavailable_shot_planning_is_not_penalised(self):
        metrics = {**NOMINAL, "shot_planning": {"available": False, "issues": []}}
        self.assertEqual(quality.score_generation(metrics, _big_file()), (100, []))

    def test_shot_planning_issues_are_penalised(self):
        metrics = {**NOMINAL, "shot_planning": {
            "available": True, "issues": ["shotType 'medium' domine la vidéo (5/6 plans) : varie davantage le cadrage"],
        }}
        score, flags = quality.score_generation(metrics, _big_file())
        self.assertEqual(score, 95)
        self.assertTrue(any("Planification des plans" in f for f in flags))

    def test_shot_planning_penalty_is_capped(self):
        metrics = {**NOMINAL, "shot_planning": {"available": True, "issues": ["a", "b", "c", "d", "e", "f"]}}
        score, _ = quality.score_generation(metrics, _big_file())
        self.assertEqual(score, 80)  # 6*5=30, plafonné à 20

    def test_no_motion_direction_key_is_backward_compatible(self):
        self.assertEqual(quality.score_generation(NOMINAL, _big_file()), (100, []))

    def test_unavailable_motion_direction_is_not_penalised(self):
        metrics = {**NOMINAL, "motion_direction": {"available": False, "issues": []}}
        self.assertEqual(quality.score_generation(metrics, _big_file()), (100, []))

    def test_motion_direction_issues_are_penalised(self):
        metrics = {**NOMINAL, "motion_direction": {
            "available": True, "issues": ["mouvement 'in' domine (5/6 plans)"],
        }}
        score, flags = quality.score_generation(metrics, _big_file())
        self.assertEqual(score, 97)
        self.assertTrue(any("Mouvement de caméra" in f for f in flags))

    def test_motion_direction_penalty_is_capped(self):
        metrics = {**NOMINAL, "motion_direction": {"available": True, "issues": ["a", "b", "c", "d", "e"]}}
        score, _ = quality.score_generation(metrics, _big_file())
        self.assertEqual(score, 90)  # 5*3=15, plafonné à 10

    def test_no_visual_fallbacks_key_is_backward_compatible(self):
        self.assertEqual(quality.score_generation(NOMINAL, _big_file()), (100, []))

    def test_style_preserving_fallback_is_not_penalised(self):
        metrics = {**NOMINAL, "visual_fallbacks": [{
            "blockIndex": 3, "requestedVisualStyle": "cinematic_real", "assetStrategy": "ai_image",
            "failureType": "content_policy", "fallbackStrategy": "reuse_same_video_scene",
            "fallbackSource": 2, "styleIntegrityPreserved": True,
        }]}
        self.assertEqual(quality.score_generation(metrics, _big_file()), (100, []))

    def test_style_breaking_fallback_is_penalised(self):
        metrics = {**NOMINAL, "visual_fallbacks": [{
            "blockIndex": 5, "requestedVisualStyle": "cinematic_real", "assetStrategy": "ai_image",
            "failureType": "content_policy", "fallbackStrategy": "reuse_same_video_scene",
            "fallbackSource": 4, "styleIntegrityPreserved": False,
        }]}
        score, flags = quality.score_generation(metrics, _big_file())
        self.assertEqual(score, 85)
        self.assertTrue(any("Intégrité de style cassée" in f for f in flags))

    def test_style_breaking_penalty_is_capped(self):
        events = [{"blockIndex": i, "styleIntegrityPreserved": False, "failureType": "x", "fallbackStrategy": "y"} for i in range(4)]
        metrics = {**NOMINAL, "visual_fallbacks": events}
        score, _flags = quality.score_generation(metrics, _big_file())
        self.assertEqual(score, 70)  # 4*15=60, plafonné à 30

    def test_score_never_negative(self):
        metrics = {**NOMINAL, "total_duration": 2, "hook_duration": 10,
                   "max_shot_duration": 10, "blocks_with_image": 0, "n_cues": 100,
                   "editorial": {"score": 0, "issues": []}}
        score, _ = quality.score_generation(metrics, "/nope.mp4")
        self.assertGreaterEqual(score, 0)


if __name__ == "__main__":
    unittest.main()
