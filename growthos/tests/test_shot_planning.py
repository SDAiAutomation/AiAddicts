import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import shot_planning


def _blocks(shot_types, roles=None):
    roles = roles or (["hook"] + ["point"] * (len(shot_types) - 2) + ["cta"] if len(shot_types) > 1 else ["hook"])
    return [{"role": role, "text": f"bloc {i}", "shotType": shot} if shot else {"role": role, "text": f"bloc {i}"}
            for i, (role, shot) in enumerate(zip(roles, shot_types))]


class TestAnalyzeShotDiversity(unittest.TestCase):
    def test_no_shot_types_at_all_is_unavailable_and_never_penalised(self):
        blocks = [{"role": "hook", "text": "x"}, {"role": "cta", "text": "y"}]
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertEqual(result, {"available": False, "issues": []})

    def test_old_script_without_the_field_is_backward_compatible(self):
        # Un script généré avant Phase 1 : aucun bloc n'a jamais entendu parler de shotType.
        blocks = [{"role": "hook", "text": "x", "visual": "y"}] * 5
        self.assertFalse(shot_planning.analyze_shot_diversity(blocks)["available"])

    def test_consecutive_identical_shot_types_are_flagged(self):
        blocks = _blocks(["wide", "medium", "medium", "close_up", "insert"])
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertTrue(result["available"])
        self.assertTrue(any("répété" in issue for issue in result["issues"]))

    def test_non_adjacent_repeat_is_not_flagged_as_consecutive(self):
        # bloc du milieu sans shotType : la paire n'est plus adjacente.
        blocks = [
            {"role": "hook", "text": "a", "shotType": "medium"},
            {"role": "point", "text": "b"},
            {"role": "point", "text": "c", "shotType": "medium"},
            {"role": "cta", "text": "d", "shotType": "wide"},
        ]
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertFalse(any("répété" in issue for issue in result["issues"]))

    def test_cta_is_exempt_from_the_consecutive_repeat_rule(self):
        blocks = [
            {"role": "hook", "text": "a", "shotType": "medium"},
            {"role": "point", "text": "b", "shotType": "medium"},
            {"role": "cta", "text": "c", "shotType": "medium"},
        ]
        result = shot_planning.analyze_shot_diversity(blocks)
        # une seule répétition flaguée (hook->point), pas point->cta
        repeats = [i for i in result["issues"] if "répété" in i]
        self.assertEqual(len(repeats), 1)

    def test_dominant_shot_type_is_flagged(self):
        blocks = _blocks(["medium", "medium", "medium", "medium", "wide"])
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertTrue(any("domine" in issue for issue in result["issues"]))

    def test_balanced_shot_types_are_not_flagged_as_dominant(self):
        blocks = _blocks(["wide", "medium", "close_up", "insert", "pov"])
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertFalse(any("domine" in issue for issue in result["issues"]))

    def test_excessive_pov_is_flagged(self):
        blocks = _blocks(["pov", "pov", "medium", "wide"])
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertTrue(any("pov" in issue and "occasionnel" in issue for issue in result["issues"]))

    def test_occasional_pov_is_not_flagged(self):
        blocks = _blocks(["pov", "medium", "wide", "close_up", "insert", "medium"])
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertFalse(any("occasionnel" in issue for issue in result["issues"]))

    def test_small_scripts_skip_ratio_checks(self):
        # 3 blocs, tous identiques : trop peu de données pour un ratio fiable,
        # seule la règle "consécutif" s'applique.
        blocks = _blocks(["medium", "medium", "medium"])
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertFalse(any("domine" in issue for issue in result["issues"]))

    def test_partial_coverage_is_flagged(self):
        blocks = [
            {"role": "hook", "text": "a", "shotType": "medium"},
            {"role": "point", "text": "b"},
            {"role": "cta", "text": "c"},
        ]
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertTrue(any("sans shotType" in issue for issue in result["issues"]))

    def test_invalid_shot_type_value_is_treated_as_absent(self):
        blocks = [{"role": "hook", "text": "a", "shotType": "extreme_wide"}]
        result = shot_planning.analyze_shot_diversity(blocks)
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
