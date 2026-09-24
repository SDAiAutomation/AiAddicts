import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import assembler, originality


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


class TestQualityFields(unittest.TestCase):
    def test_none_metrics_returns_empty_dict(self):
        self.assertEqual(assembler._quality_fields(None, _big_file()), {})

    def test_no_originality_key_is_backward_compatible(self):
        fields = assembler._quality_fields(dict(NOMINAL), _big_file())
        self.assertNotIn("status", fields)
        self.assertNotIn("originality_report", fields)

    def test_too_similar_forces_quality_check_and_adds_flag(self):
        result = originality.OriginalityResult(
            too_similar=True, overall_similarity=88, compared_count=12, history_available=True,
            dimensions=[{"name": "concept", "similarity": 88, "matchedVideoIds": ["abc"], "explanation": "même twist"}],
            matched_video_ids=["abc"], suggestion="changer d'espèce et de décor",
        )
        fields = assembler._quality_fields({**NOMINAL, "originality": result}, _big_file())
        self.assertEqual(fields["status"], "quality_check")
        self.assertTrue(any("ressemblance forte" in f.lower() for f in fields["quality_flags"]))
        self.assertEqual(fields["originality_report"]["tooSimilar"], True)
        self.assertEqual(fields["originality_report"]["matchedVideoIds"], ["abc"])

    def test_not_too_similar_does_not_force_quality_check(self):
        result = originality.OriginalityResult(
            too_similar=False, overall_similarity=20, compared_count=12, history_available=True,
        )
        fields = assembler._quality_fields({**NOMINAL, "originality": result}, _big_file())
        self.assertNotIn("status", fields)
        self.assertEqual(fields["originality_report"]["tooSimilar"], False)

    def test_warn_adds_flag_without_forcing_quality_check(self):
        result = originality.OriginalityResult(
            too_similar=False, warn=True, overall_similarity=80, compared_count=12, history_available=True,
            matched_video_ids=["abc"],
        )
        fields = assembler._quality_fields({**NOMINAL, "originality": result}, _big_file())
        self.assertNotIn("status", fields)
        self.assertTrue(any("ressemblance notable" in f.lower() for f in fields["quality_flags"]))
        self.assertFalse(any("ressemblance forte" in f.lower() for f in fields["quality_flags"]))
        self.assertEqual(fields["originality_report"]["warn"], True)

    def test_history_unavailable_adds_distinct_flag_without_forcing_status(self):
        result = originality.OriginalityResult(
            too_similar=False, overall_similarity=0, compared_count=0, history_available=False,
        )
        fields = assembler._quality_fields({**NOMINAL, "originality": result}, _big_file())
        self.assertNotIn("status", fields)
        self.assertTrue(any("historique insuffisant" in f.lower() for f in fields["quality_flags"]))
        self.assertFalse(any("ressemblance forte" in f.lower() for f in fields["quality_flags"]))

    def test_originality_none_is_ignored(self):
        fields = assembler._quality_fields({**NOMINAL, "originality": None}, _big_file())
        self.assertNotIn("originality_report", fields)
        self.assertNotIn("status", fields)

    def test_low_score_and_too_similar_both_reflected(self):
        result = originality.OriginalityResult(
            too_similar=True, overall_similarity=95, compared_count=5, history_available=True,
            matched_video_ids=["x", "y"],
        )
        metrics = {**NOMINAL, "editorial": {"score": 40, "issues": ["hook générique"]}, "originality": result}
        fields = assembler._quality_fields(metrics, _big_file())
        self.assertEqual(fields["status"], "quality_check")
        self.assertEqual(len(fields["quality_flags"]), 2)  # score éditorial faible + originalité


if __name__ == "__main__":
    unittest.main()
