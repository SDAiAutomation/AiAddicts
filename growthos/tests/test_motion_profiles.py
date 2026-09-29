import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import motion_profiles


class TestResolveMotionProfile(unittest.TestCase):
    def test_known_styles_map_to_expected_profiles(self):
        self.assertEqual(motion_profiles.resolve_motion_profile("cinematic_real"), "cinematic")
        self.assertEqual(motion_profiles.resolve_motion_profile("storybook"), "gentle")
        self.assertEqual(motion_profiles.resolve_motion_profile("comic_book"), "comic")
        self.assertEqual(motion_profiles.resolve_motion_profile("anime"), "energetic")
        self.assertEqual(motion_profiles.resolve_motion_profile("flat_color"), "kinetic")
        self.assertEqual(motion_profiles.resolve_motion_profile("stock_footage"), "none")
        self.assertEqual(motion_profiles.resolve_motion_profile("motion_graphics"), "kinetic")

    def test_legacy_ids_still_resolve(self):
        self.assertEqual(motion_profiles.resolve_motion_profile("pixar_3d"), "cinematic")
        self.assertEqual(motion_profiles.resolve_motion_profile("gta_loading"), "energetic")
        self.assertEqual(motion_profiles.resolve_motion_profile("anime_3d"), "cinematic")

    def test_unknown_or_missing_style_falls_back_to_default(self):
        self.assertEqual(motion_profiles.resolve_motion_profile(None), motion_profiles.DEFAULT_PROFILE)
        self.assertEqual(motion_profiles.resolve_motion_profile(""), motion_profiles.DEFAULT_PROFILE)
        self.assertEqual(motion_profiles.resolve_motion_profile("un style CLI libre"), motion_profiles.DEFAULT_PROFILE)


class TestMotionProfilesOnlyUseKnownMoves(unittest.TestCase):
    def test_every_profile_only_lists_real_kb_moves(self):
        from engine.video import _KB_MOVES

        for profile, moves in motion_profiles.MOTION_PROFILES.items():
            for move in moves:
                self.assertIn(move, _KB_MOVES, f"{profile!r} lists unknown move {move!r}")


class TestSelectMotion(unittest.TestCase):
    def test_deterministic_same_inputs_same_output(self):
        a = motion_profiles.select_motion("cinematic", 3, "wide", "establish", "une rue déserte")
        b = motion_profiles.select_motion("cinematic", 3, "wide", "establish", "une rue déserte")
        self.assertEqual(a, b)

    def test_different_block_index_can_change_the_choice(self):
        choices = {
            motion_profiles.select_motion("cinematic", i, None, None, "")
            for i in range(1, 20)
        }
        self.assertGreater(len(choices), 1)  # pas toujours le même mouvement

    def test_choice_always_within_the_profile(self):
        for i in range(1, 30):
            move = motion_profiles.select_motion("gentle", i, None, None, f"texte {i}")
            self.assertIn(move, motion_profiles.MOTION_PROFILES["gentle"])

    def test_kinetic_profile_has_a_safe_fallback(self):
        self.assertEqual(motion_profiles.select_motion("kinetic", 1), "in_slow")

    def test_close_up_prefers_the_subtle_hint(self):
        move = motion_profiles.select_motion("cinematic", 5, "close_up", None, "un visage")
        self.assertEqual(move, "in_slow")

    def test_insert_prefers_a_push_in(self):
        move = motion_profiles.select_motion("cinematic", 5, "insert", None, "une clé posée sur la table")
        self.assertIn(move, ("in", "in_slow"))

    def test_wide_prefers_pan_or_drift(self):
        move = motion_profiles.select_motion("cinematic", 5, "wide", None, "une rue vide")
        self.assertIn(move, ("left", "right", "up", "out"))

    def test_hint_never_escapes_the_profile(self):
        # "gentle" ne contient pas "out" : le hint "wide" doit rester dans le profil.
        move = motion_profiles.select_motion("gentle", 5, "wide", None, "une plaine")
        self.assertIn(move, motion_profiles.MOTION_PROFILES["gentle"])

    def test_avoids_repeating_the_previous_move_when_an_alternative_exists(self):
        move = motion_profiles.select_motion("cinematic", 4, None, None, "texte", previous_move="left")
        # Un seul mouvement possible ("left") -> même valeur acceptée ; sinon jamais "left".
        if len(motion_profiles.MOTION_PROFILES["cinematic"]) > 1:
            self.assertNotEqual(move, "left")

    def test_unknown_profile_falls_back_to_default(self):
        move = motion_profiles.select_motion("not_a_real_profile", 1)
        self.assertIn(move, motion_profiles.MOTION_PROFILES[motion_profiles.DEFAULT_PROFILE])


class TestResolveMotionSequence(unittest.TestCase):
    def test_video_and_none_shots_get_no_motion(self):
        shots = [(1, "clip.mp4", 3.0, 0.0), (2, None, 3.0, 0.0)]
        blocks = [{"shotType": "wide"}, {"shotType": "wide"}]
        self.assertEqual(motion_profiles.resolve_motion_sequence(shots, blocks, "cinematic"), [None, None])

    def test_kinetic_profile_never_assigns_motion(self):
        shots = [(1, "scene.jpg", 3.0, 0.0), (2, "scene2.jpg", 3.0, 0.0)]
        blocks = [{}, {}]
        self.assertEqual(motion_profiles.resolve_motion_sequence(shots, blocks, "kinetic"), [None, None])

    def test_image_shots_get_a_move_from_the_profile(self):
        shots = [(1, "a.jpg", 3.0, 0.0), (2, "b.jpg", 3.0, 0.0), (3, "c.jpg", 3.0, 0.0)]
        blocks = [{}, {}, {}]
        moves = motion_profiles.resolve_motion_sequence(shots, blocks, "cinematic")
        self.assertEqual(len(moves), 3)
        for move in moves:
            self.assertIn(move, motion_profiles.MOTION_PROFILES["cinematic"])

    def test_reproducible_across_calls(self):
        shots = [(1, "a.jpg", 3.0, 0.0), (2, "b.jpg", 4.0, 0.0), (2, "b.jpg", 4.0, 3.0)]
        blocks = [{"shotType": "wide"}, {"shotType": "close_up", "visualPurpose": "reveal"}]
        first = motion_profiles.resolve_motion_sequence(shots, blocks, "cinematic")
        second = motion_profiles.resolve_motion_sequence(shots, blocks, "cinematic")
        self.assertEqual(first, second)

    def test_split_block_shots_reuse_the_same_blocks_metadata_without_crashing(self):
        # Un bloc découpé en plusieurs plans (engine.video.plan_shots) partage
        # le même block_index plusieurs fois de suite.
        shots = [(1, "a.jpg", 3.0, 0.0), (1, "a.jpg", 3.0, 3.0), (1, "a.jpg", 1.0, 6.0)]
        blocks = [{"shotType": "insert"}]
        moves = motion_profiles.resolve_motion_sequence(shots, blocks, "cinematic")
        self.assertEqual(len(moves), 3)


class TestAnalyzeMotionDiversity(unittest.TestCase):
    def test_no_image_backed_shots_is_unavailable(self):
        self.assertEqual(motion_profiles.analyze_motion_diversity([None, None]), {"available": False, "issues": []})

    def test_consecutive_repeat_is_flagged(self):
        result = motion_profiles.analyze_motion_diversity(["left", "left", "right"])
        self.assertTrue(result["available"])
        self.assertTrue(any("répété" in issue for issue in result["issues"]))

    def test_dominant_move_is_flagged(self):
        result = motion_profiles.analyze_motion_diversity(["in", "in", "in", "in", "left"])
        self.assertTrue(any("domine" in issue for issue in result["issues"]))

    def test_balanced_moves_are_not_flagged(self):
        result = motion_profiles.analyze_motion_diversity(["left", "right", "up", "out", "in_slow"])
        self.assertEqual(result["issues"], [])

    def test_small_sequences_skip_the_dominance_check(self):
        result = motion_profiles.analyze_motion_diversity(["left", "right", "up"])
        self.assertFalse(any("domine" in issue for issue in result["issues"]))


class TestAnalyzeMotionDiversityCollapsesSplitShots(unittest.TestCase):
    """Phase 2.6 (benchmark fix) — reproduces the exact A/cinematic_real
    benchmark defect: a hook block long enough to be split into 2 sub-shots
    (engine.video.plan_shots) legitimately holds one motion across both, but
    `analyze_motion_diversity` flagged it as a repeated-motion violation —
    and repeated it once per split block, 5 times on a single 6-block video."""

    def test_split_block_holding_one_move_is_not_flagged(self):
        # bloc 1 découpé en 2 plans (même block_index=1, même mouvement,
        # légitime) ; blocs 2 et 3 non découpés, mouvements variés.
        shots = [(1, "a.jpg", 3.0, 0.0), (1, "a.jpg", 1.0, 3.0), (2, "b.jpg", 2.0, 0.0), (3, "c.jpg", 2.0, 0.0)]
        moves = ["in_slow", "in_slow", "left", "right"]
        result = motion_profiles.analyze_motion_diversity(moves, shots=shots)
        self.assertEqual(result["issues"], [])

    def test_reproduces_the_benchmark_scenario_five_split_shots_one_warning_max(self):
        # 6 blocs, chacun découpé en 2 plans (durée > 3s) : sans collapse,
        # les 6 paires identiques déclenchaient 6 avertissements "répété".
        shots = []
        moves = []
        for block_index, move in enumerate(("in_slow", "out", "right", "left", "in_slow", "in_slow"), start=1):
            shots.append((block_index, f"img{block_index}.jpg", 3.0, 0.0))
            shots.append((block_index, f"img{block_index}.jpg", 1.0, 3.0))
            moves.append(move)
            moves.append(move)  # même mouvement tenu sur le sous-plan, légitime
        result = motion_profiles.analyze_motion_diversity(moves, shots=shots)
        repeats = [i for i in result["issues"] if "répété" in i]
        # Seule une VRAIE répétition entre blocs consécutifs distincts
        # (in_slow au bloc 5 puis 6) doit rester — jamais les 6 sous-plans.
        self.assertEqual(len(repeats), 1)

    def test_a_real_cross_block_repeat_still_gets_flagged(self):
        shots = [(1, "a.jpg", 3.0, 0.0), (1, "a.jpg", 1.0, 3.0), (2, "b.jpg", 3.0, 0.0)]
        moves = ["in_slow", "in_slow", "in_slow"]  # bloc 1 (tenu) PUIS bloc 2 : vraie répétition
        result = motion_profiles.analyze_motion_diversity(moves, shots=shots)
        self.assertTrue(any("répété" in i for i in result["issues"]))

    def test_without_shots_falls_back_to_flat_per_shot_analysis(self):
        # Rétro-compatibilité explicite : un appelant qui ne passe pas `shots`
        # garde l'ancien comportement (analyse brute par plan).
        moves = ["in_slow", "in_slow"]
        result = motion_profiles.analyze_motion_diversity(moves)
        self.assertTrue(any("répété" in i for i in result["issues"]))


if __name__ == "__main__":
    unittest.main()
