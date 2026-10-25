"""Contract v2.1 (animation schema 2): long-form duration targets, a narrator, editorial provenance, and the Standard adapter.
Schema 1 behaviour is pinned by the shared fixture (test_contract.py); these tests pin what is new and that nothing leaks into schema 1."""
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from growthos.engine.story_animation import contract, pipeline, quality, shotplan, story_adapter
from growthos.engine.story_animation.test_timeline_lib import alignment

FX = Path(__file__).parent / "fixtures"
CATALOG = pipeline.RIG_V1_CATALOG
NAMES = ("story_v21_la_file", "story_v21_parapluie", "story_v21_ville_sans_mots")


def load(name):
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))


def errors_of(story):
    return contract.validate_animation_story(story, CATALOG)


class ThreePilotScenarios(unittest.TestCase):
    def test_each_scenario_is_a_valid_schema_2_story(self):
        for name in NAMES:
            with self.subTest(name):
                self.assertEqual(errors_of(load(name)["story"]), [])

    def test_each_scenario_reaches_its_target_at_the_fast_rate_and_stays_in_budget_at_the_slow_rate(self):
        for name in NAMES:
            story = load(name)["story"]
            chars = sum(len(s["dialogue"]) for s in story["shots"])
            fast = chars / contract.SPEECH_CHARS_PER_SECOND_FAST + contract.FIXED_SECONDS
            slow = chars / contract.SPEECH_CHARS_PER_SECOND_SLOW + contract.FIXED_SECONDS
            with self.subTest(name):
                self.assertGreaterEqual(fast, 60.0)
                self.assertGreaterEqual(fast, 0.85 * story["duration_target_s"])
                self.assertLessEqual(slow, 1.3 * story["duration_target_s"])
                self.assertLessEqual(slow, contract.LIMITS[2]["max_duration"])

    def test_every_statement_of_fact_cites_a_source_and_fiction_stays_fiction(self):
        for name in NAMES:
            story = load(name)["story"]
            for shot in story["shots"]:
                if shot["nature"] == "fact":
                    self.assertTrue(shot["source_ids"], (name, shot["id"]))
        self.assertEqual({s["nature"] for s in load("story_v21_parapluie")["story"]["shots"]}, {"fiction"})

    def test_a_secondary_or_unverified_source_is_never_labelled_primary(self):
        for name in NAMES:
            for src in load(name)["story"]["editorial"]["sources"]:
                self.assertIn(src["verification"], ("secondary", "unverified"))


class SchemaOneIsUntouched(unittest.TestCase):
    def test_new_fields_are_refused_in_schema_1(self):
        story = load("story_v21_parapluie")["story"]
        story["animation_schema_version"] = 1
        story["shots"] = story["shots"][:3]   # schema 1 stops at 12 shots, so keep a few and read the field errors
        found = " ".join(errors_of(story))
        for key in ("duration_target_s", "narrator", "editorial"):
            self.assertIn(f"story.{key} requires animation_schema_version 2", found)
        self.assertIn("shots[0].nature requires animation_schema_version 2", found)

    def test_schema_1_limits_are_the_old_ones(self):
        self.assertEqual(contract.LIMITS[1], {"max_shots": 12, "max_duration": 60.0, "max_dialogue": 1200})

    def test_an_unknown_schema_is_refused(self):
        story = load("story_v21_parapluie")["story"]
        story["animation_schema_version"] = 3
        self.assertTrue(any("not supported" in e for e in errors_of(story)))


class Schema2Rules(unittest.TestCase):
    def setUp(self):
        self.story = load("story_v21_ville_sans_mots")["story"]

    def assertRefused(self, story, text):
        self.assertTrue(any(text in e for e in errors_of(story)), errors_of(story)[:4])

    def test_targets_are_a_closed_list(self):
        for bad in (45, 300, True, "90"):
            story = copy.deepcopy(self.story)
            story["duration_target_s"] = bad
            self.assertRefused(story, "duration_target_s must be one of")

    def test_a_text_too_short_or_too_long_for_its_target_is_refused_before_any_credit(self):
        short = copy.deepcopy(self.story)
        short["shots"] = short["shots"][:5]
        self.assertRefused(short, "too short for a 90s target")
        long_story = copy.deepcopy(self.story)
        long_story["duration_target_s"] = 60
        self.assertRefused(long_story, "too long for a 60s target")

    def test_the_narrator_is_a_voice_not_a_character(self):
        story = copy.deepcopy(self.story)
        story["narrator"]["id"] = "pip"
        self.assertRefused(story, "narrator.id must differ from every character id")
        story = copy.deepcopy(self.story)
        story["shots"][0]["speaker_id"] = "someone"
        self.assertRefused(story, "speaker_id is not a known character or the narrator")

    def test_a_narrator_shot_cannot_be_a_close_up_and_a_character_shot_still_needs_its_speaker_on_screen(self):
        story = copy.deepcopy(self.story)
        idx = next(i for i, s in enumerate(story["shots"]) if s["speaker_id"] == "narrator")
        story["shots"][idx]["shot_type"] = "close_up"
        self.assertRefused(story, "a narrator shot cannot be a close_up")
        story = copy.deepcopy(self.story)
        idx = next(i for i, s in enumerate(story["shots"]) if s["speaker_id"] == "pip")
        story["shots"][idx]["actors"] = [a for a in story["shots"][idx]["actors"] if a["character_id"] != "pip"]
        self.assertRefused(story, "speaker_id must also appear in actors")

    def test_a_narrator_shot_may_show_the_setting_alone_but_a_character_shot_may_not(self):
        story = copy.deepcopy(self.story)
        idx = next(i for i, s in enumerate(story["shots"]) if s["speaker_id"] == "narrator")
        story["shots"][idx]["actors"] = []
        self.assertEqual(errors_of(story), [])
        story = copy.deepcopy(self.story)
        idx = next(i for i, s in enumerate(story["shots"]) if s["speaker_id"] == "pip")
        story["shots"][idx]["actors"] = []
        self.assertRefused(story, "actors must be a nonempty list")

    def test_a_fact_needs_a_source_and_a_source_must_exist(self):
        story = copy.deepcopy(self.story)
        idx = next(i for i, s in enumerate(story["shots"]) if s["nature"] == "fact")
        story["shots"][idx]["source_ids"] = []
        self.assertRefused(story, "states a fact: it needs at least one source_ids entry")
        story = copy.deepcopy(self.story)
        story["shots"][idx]["source_ids"] = ["nope"]
        self.assertRefused(story, "source_ids must list at most 5 ids of editorial.sources")

    def test_a_pure_fiction_cannot_contain_facts_and_a_mixed_story_must_announce_its_fiction(self):
        story = copy.deepcopy(self.story)
        story["editorial"]["kind"] = "fiction"
        self.assertRefused(story, "is not allowed when editorial.kind is 'fiction'")
        story = copy.deepcopy(self.story)
        del story["editorial"]["disclaimer"]
        self.assertRefused(story, "editorial.disclaimer is required when kind is 'mixed'")

    def test_sources_are_clean(self):
        story = copy.deepcopy(self.story)
        story["editorial"]["sources"][1]["url"] = "http://insecure.example/x"
        self.assertRefused(story, "url must be an https URL")
        story = copy.deepcopy(self.story)
        story["editorial"]["sources"][0]["verification"] = "certain"
        self.assertRefused(story, "verification must be one of")
        story = copy.deepcopy(self.story)
        story["editorial"]["sources"][1]["id"] = story["editorial"]["sources"][0]["id"]
        self.assertRefused(story, "is duplicated")
        story = copy.deepcopy(self.story)
        story["editorial"]["genre"] = "horror_marketing"
        self.assertRefused(story, "editorial.genre must be one of")

    def test_the_schema_2_limits(self):
        story = copy.deepcopy(self.story)
        story.pop("duration_target_s")
        template = story["shots"][1]
        story["shots"] = [dict(copy.deepcopy(template), id=f"x{i}", dialogue="Une phrase courte.") for i in range(contract.LIMITS[2]["max_shots"])]
        self.assertEqual(errors_of(story), [])
        story["shots"].append(dict(copy.deepcopy(template), id="x_extra", dialogue="Une de trop."))
        self.assertRefused(story, "at most 40 shots")


class NarratorPipeline(unittest.TestCase):
    """The whole pipeline with fake ports on a 15-scene story that has a narrator: roles, voices, limits, nothing paid."""

    def run_story(self, name):
        calls = {"voices": [], "reserved": 0}

        def synth(text, voice, wav):
            calls["voices"].append(voice)
            dur = len(text) / contract.SPEECH_CHARS_PER_SECOND_FAST
            n = int(dur * 24)
            return {"duration_s": dur, "alignment": alignment(text, dur / len(text)), "envelope": [1.0] * n}

        captured = {}
        ports = pipeline.Ports(
            authorize=lambda: None, moderate=lambda s: None, ready=lambda: [],
            estimate=lambda seconds, chars: SimpleNamespace(render_seconds=seconds * 4, tts_chars=chars),
            reserve_credit=lambda: calls.__setitem__("reserved", calls["reserved"] + 1) or True, refund_credit=lambda: None,
            record_event=lambda *a, **k: None, synthesize=synth,
            render=lambda tl, workdir: captured.update(tl) or SimpleNamespace(video_path=Path("s.mp4")),
            mix=lambda rendered, starts, tl, out: Path("final.mp4"), check_quality=lambda final: [],
            publish=lambda final, tl, review: {"video_url": "https://example.test/v.mp4"}, catalog=CATALOG,
        )
        pipeline.run(load(name), ports, Path("unused"))
        return captured, calls

    def test_each_scenario_runs_end_to_end_with_a_narrator_and_a_duration_above_60_s(self):
        for name in NAMES:
            with self.subTest(name):
                tl, calls = self.run_story(name)
                self.assertEqual(calls["reserved"], 1)
                self.assertIn("voice_narr_1", calls["voices"])
                self.assertIn("narrator", {line["who"] for line in tl["lines"]})
                self.assertGreaterEqual(tl["total"], 60.0)
                self.assertLessEqual(tl["total"], contract.LIMITS[2]["max_duration"])
                self.assertEqual([s["speaker"] for s in tl["shots"]], [line["who"] for line in tl["lines"]])
                self.assertEqual(tl["shots"][-1]["end"], tl["total"])

    def test_a_schema_1_story_is_still_limited_to_60_s(self):
        with self.assertRaises(ValueError):
            from growthos.engine.story_animation import timeline as timeline_lib
            lines = [{"who": "pip", "text": "x", "duration_s": 30.0, "alignment": alignment("x", 30.0), "envelope": [1.0] * 720}] * 3
            timeline_lib.build_timeline(lines)


class FinalDurationIsMeasured(unittest.TestCase):
    REPORT = {"video_duration_s": 91.0, "audio_duration_s": 91.0, "width": 1080, "height": 1920, "fps": 24, "size_bytes": 20_000_000,
              "black": [], "freeze": [], "mean_volume_db": -20.0, "max_volume_db": -3.0}
    EXPECTED = {"width": 1080, "height": 1920, "fps": 24}

    def kinds(self, duration, target):
        report = dict(self.REPORT, video_duration_s=duration, audio_duration_s=duration)
        return {(p.kind, p.severity) for p in quality.judge_media(report, dict(self.EXPECTED, target_s=target))}

    def test_on_target_passes_and_without_a_target_nothing_changes(self):
        self.assertEqual(self.kinds(91.0, 90), set())
        self.assertEqual(quality.judge_media(dict(self.REPORT, video_duration_s=30.0, audio_duration_s=30.0), self.EXPECTED), [])

    def test_below_60_s_is_blocking_and_outside_the_tolerance_band_is_for_review(self):
        self.assertEqual(self.kinds(55.0, 60), {("min_duration", quality.BLOCKING)})
        self.assertEqual(self.kinds(70.0, 90), {("target_duration", quality.REVIEW)})
        self.assertEqual(self.kinds(120.0, 90), {("target_duration", quality.REVIEW)})
        self.assertEqual(self.kinds(76.5, 90), set())   # 0.85 x 90 is inside the band
        self.assertEqual(self.kinds(108.0, 90), set())  # 1.2 x 90 is inside the band


class StandardAdapter(unittest.TestCase):
    NARRATOR = {"id": "narrator", "name": "Narrateur", "voice_id": "voice_narr_1"}
    CHARACTERS = [{"id": "pip", "name": "Pip", "voice_id": "voice_pip_1", "pack_id": "pip_v1"},
                  {"id": "rosette", "name": "Madame Rosette", "voice_id": "voice_ros_1", "pack_id": "rosette_v1"}]

    def adapt(self, script=None, **kw):
        script = script or json.loads((FX / "standard_script_la_file.json").read_text(encoding="utf-8"))
        return story_adapter.adapt(script, narrator=self.NARRATOR, characters=self.CHARACTERS, duration_target_s=90, **kw)

    def test_a_standard_script_becomes_a_valid_story_without_a_second_narrative_engine(self):
        result = self.adapt()
        self.assertEqual(result.errors, [])
        story = result.script["story"]
        self.assertEqual(result.script["content_format"], "story")
        self.assertEqual(story["animation_schema_version"], 2)
        self.assertEqual(len(story["shots"]), 15)
        self.assertEqual([s["dialogue"] for s in story["shots"]][1], "Madame Rosette, pourquoi tout le monde fait la queue devant cette porte ?")
        self.assertEqual({s["speaker_id"] for s in story["shots"]}, {"narrator", "pip", "rosette"})

    def test_narrator_shots_show_the_listeners_and_never_a_close_up(self):
        story = self.adapt().script["story"]
        for shot in story["shots"]:
            if shot["speaker_id"] == "narrator":
                self.assertNotEqual(shot["shot_type"], "close_up")
                self.assertEqual({a["character_id"] for a in shot["actors"]}, {"pip", "rosette"})

    def test_the_standard_validator_stays_the_authority(self):
        bad = json.loads((FX / "standard_script_la_file.json").read_text(encoding="utf-8"))
        bad["blocks"][2]["role"] = "monologue"
        with self.assertRaises(ValueError):
            self.adapt(bad)

    def test_standard_retention_diagnostics_are_reported_not_re_implemented(self):
        result = self.adapt()
        self.assertIsInstance(result.retention_issues, list)

    def test_a_long_block_is_cut_at_sentence_ends_under_the_scene_limit(self):
        text = " ".join(f"Phrase numéro {i} qui continue assez longtemps pour remplir le bloc." for i in range(12))
        pieces = story_adapter.split_text(text)
        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(p) <= contract.MAX_SHOT_DIALOGUE_CHARS for p in pieces))
        self.assertEqual(" ".join(pieces), text)
        self.assertEqual(len(story_adapter.split_text("x" * 900)), 3)

    def test_a_script_that_cannot_reach_its_target_is_reported_by_the_contract(self):
        script = json.loads((FX / "standard_script_la_file.json").read_text(encoding="utf-8"))
        script["blocks"] = script["blocks"][:4]
        self.assertTrue(any("too short" in e for e in self.adapt(script).errors))


if __name__ == "__main__":
    unittest.main()
