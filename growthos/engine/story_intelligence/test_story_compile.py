import unittest
from copy import deepcopy

from growthos.engine import story_compile as sc


def make():
    return {
        "content_format": "story", "title": "T", "niche": "n", "account": "a",
        "story": {
            "target_duration_s": 8,
            "characters": [
                {"id": "neo", "name": "Néo", "voice_id": "v1", "description": "un jeune renard roux"},
                {"id": "orion", "name": "Orion", "voice_id": "v2", "description": "un vieux hibou gris"},
            ],
            "shots": [
                {"id": "s1", "speaker_id": "neo", "dialogue": "Pourquoi ?", "duration_s": 3},
                {"id": "s2", "speaker_id": "orion", "dialogue": "Écoute.", "duration_s": 3},
                {"id": "s3", "speaker_id": "neo", "dialogue": "Merci.", "duration_s": 2},
            ],
        },
    }


class StoryCompileTests(unittest.TestCase):
    def test_compiles_one_block_per_shot_with_speaker_voice(self):
        out = sc.compile_story(make())
        self.assertEqual([b["voice_id"] for b in out["blocks"]], ["v1", "v2", "v1"])
        self.assertEqual([b["role"] for b in out["blocks"]], ["hook", "point", "cta"])
        self.assertEqual(out["characters"][0], {"name": "Néo", "description": "un jeune renard roux"})

    def test_does_not_mutate_input(self):
        s = make(); before = deepcopy(s)
        sc.compile_story(s)
        self.assertEqual(s, before)

    def test_not_story_is_returned_unchanged(self):
        s = {"content_format": "standard", "blocks": []}
        self.assertIs(sc.compile_story(s), s)

    def test_refuses_missing_voice_description_and_oversize(self):
        s = make(); s["story"]["characters"][0]["voice_id"] = ""
        self.assertTrue(any("no voice" in e for e in sc.render_errors(s)))
        s = make(); s["story"]["characters"][1]["description"] = " "
        self.assertTrue(any("no visual description" in e for e in sc.render_errors(s)))
        s = make(); s["story"]["shots"] = [dict(id=f"s{i}", speaker_id="neo", dialogue="x", duration_s=1) for i in range(13)]
        s["story"]["target_duration_s"] = 13
        self.assertTrue(any("at most" in e for e in sc.render_errors(s)))
        with self.assertRaises(ValueError):
            sc.compile_story(s)

    def test_refuses_invalid_storyboard(self):
        s = make(); s["story"]["shots"][0]["speaker_id"] = "ghost"
        self.assertTrue(sc.render_errors(s))

    def test_estimate_counts_without_any_call(self):
        e = sc.estimate(make())
        self.assertEqual((e["shots"], e["images"], e["voice_characters"], e["estimated"]), (3, 3, len("Pourquoi ?") + len("Écoute.") + len("Merci."), True))

    def test_not_wired_into_script_normalization(self):
        from growthos.engine import script
        s = make()
        self.assertIs(script.normalize_script(s), s)


if __name__ == "__main__":
    unittest.main()
