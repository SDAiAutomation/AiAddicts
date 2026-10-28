import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from growthos.engine import captions, image_style_bible
from growthos.engine.story_animation import pipeline, quality, storyboard
from growthos.engine.story_animation.renderer import RenderError, RenderResult
from growthos.engine.story_animation.test_pipeline import Harness, script

LOOKS = {"pip": {"name": "Pip", "description": "grosse tête ronde blanche, lunettes rondes"},
         "rosette": {"name": "Madame Rosette", "description": "chapeau noir à fleur rouge"}}


def sb_ports(**kw):
    defaults = dict(generate_image=lambda prompt, out: None, usd_per_image=0.05, llm_reserve_usd=0.05)
    defaults.update(kw)
    return storyboard.StoryboardPorts(**defaults)


class Selection(unittest.TestCase):
    def test_renderer_from_env(self):
        self.assertEqual(storyboard.renderer_from_env({}), "storyboard")
        self.assertEqual(storyboard.renderer_from_env({"STORY_RENDERER": "rig_v1"}), "rig_v1")
        self.assertEqual(storyboard.renderer_from_env({"STORY_RENDERER": " Storyboard "}), "storyboard")
        self.assertEqual(storyboard.renderer_from_env({"STORY_RENDERER": "; rm -rf /"}), "storyboard")


class Prompts(unittest.TestCase):
    def test_noir_style_and_present_characters_only(self):
        style = image_style_bible.resolve_story_style_bible("noir_1930")
        d = {"show": "Pip pulls a telephone out of his pocket.", "shot": "close_up", "camera": "push_in",
             "characters": ["pip"], "crowd": ["worker"]}
        prompt = storyboard.beat_prompt(d, style, LOOKS)
        self.assertIn("rubber hose", prompt)
        self.assertIn("NOIR ET BLANC", prompt)
        self.assertIn("rouge", prompt)
        self.assertIn("Pip", prompt)
        self.assertIn("lunettes rondes", prompt)
        self.assertNotIn("Rosette", prompt)
        self.assertIn("ouvrier", prompt)
        self.assertIn("Gros plan", prompt)
        self.assertIn("SANS AUCUN TEXTE", prompt)

    def test_every_story_style_resolves_and_unknown_falls_back(self):
        for sid in pipeline.STYLES:
            self.assertEqual(image_style_bible.resolve_story_style_bible(sid)["visual_style_id"], sid)
        self.assertEqual(image_style_bible.resolve_story_style_bible("../x")["visual_style_id"], "noir_1930")
        self.assertGreater(image_style_bible.resolve_story_style_bible("noir_1930")["grain"], 0)

    def test_character_looks_from_script_then_pack(self):
        story = script()["story"]
        looks = storyboard.character_looks(story, {"characters": [{"name": "Pip", "description": "un grand échalas\x00"}]})
        pip_id = next(c["id"] for c in story["characters"] if c["pack_id"] == "pip_v1")
        ros_id = next(c["id"] for c in story["characters"] if c["pack_id"] == "rosette_v1")
        self.assertEqual(looks[pip_id]["description"], "un grand échalas")
        self.assertIn("fleur rouge", looks[ros_id]["description"])
        self.assertIn("nœud papillon rouge", storyboard.PACK_LOOKS["pip_v1"])

    def test_reused_picture_gets_a_different_move(self):
        dirs = [{"camera": "push_in"}, {"camera": "push_in"}, {"camera": "pan_left"}]
        moves = storyboard.kb_moves(dirs, [None, 0, None])
        self.assertEqual(moves[0], "in")
        self.assertNotEqual(moves[1], moves[0])
        self.assertEqual(moves[2], "left")


class Costs(unittest.TestCase):
    def test_plan_is_bounded_and_counts_retries_and_llm(self):
        plan = storyboard.plan_costs(100.0, sb_ports(call_llm=lambda m, mo: ("", {}), llm_model="m"))
        self.assertEqual(plan.max_images, 40)
        self.assertEqual(plan.image_calls, 48)
        self.assertAlmostEqual(plan.images_usd, 2.4)
        self.assertAlmostEqual(plan.llm_usd, 0.1)
        self.assertEqual(storyboard.plan_costs(10_000, sb_ports()).max_images, storyboard.MAX_BEATS)
        self.assertEqual(storyboard.plan_costs(100.0, sb_ports()).llm_calls, 0)

    def test_usd_per_image_uses_token_prices_when_configured(self):
        env = {"IMAGE_PRICE_TEXT_IN_PER_M": "5", "IMAGE_PRICE_IMAGE_IN_PER_M": "8", "IMAGE_PRICE_IMAGE_OUT_PER_M": "30"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertAlmostEqual(storyboard.usd_per_image_estimate(), 0.052, places=3)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(storyboard.usd_per_image_estimate(), storyboard.FALLBACK_USD_PER_IMAGE)


class Captions(unittest.TestCase):
    def test_style_from_script(self):
        self.assertEqual(storyboard.caption_style_of({"caption_style": "neon"}), "neon")
        self.assertEqual(storyboard.caption_style_of({"caption_style": "off"}), captions.CAPTIONS_OFF)
        self.assertEqual(storyboard.caption_style_of({"caption_style": "grey_box"}), captions.DEFAULT_CAPTION_STYLE)
        self.assertEqual(storyboard.caption_style_of({}), captions.DEFAULT_CAPTION_STYLE)

    def test_off_writes_nothing_and_presets_write_ass(self):
        lines = [{"text": "Bonjour tout le monde.", "start": 0.5, "dur": 2.0, "alignment": None}]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(storyboard.write_captions(lines, 5.0, "off", Path(tmp) / "a.ass"))
            path = storyboard.write_captions(lines, 5.0, "bold_stroke", Path(tmp) / "b.ass")
            text = path.read_text(encoding="utf-8")
        self.assertIn("BONJOUR", text.upper())
        self.assertIn("PlayResY: 1920", text)

    def test_words_are_in_absolute_time(self):
        words = storyboard.caption_words([{"text": "Un deux", "start": 3.0, "dur": 1.4, "alignment": None}])
        self.assertEqual([w["text"] for w in words], ["Un", "deux"])
        self.assertAlmostEqual(words[0]["start"], 3.0)
        self.assertAlmostEqual(words[-1]["end"], 4.4)
        words = storyboard.caption_words([{"text": "Vite , matin !", "start": 0.0, "dur": 1.4, "alignment": None}])
        self.assertEqual([w["text"] for w in words], ["Vite ,", "matin !"])


class Images(unittest.TestCase):
    def gen(self, ok_indices, log):
        def generate(prompt, out):
            log.append(prompt)
            i = int(prompt)
            if i in ok_indices:
                Path(out).write_bytes(b"jpg")
                return out
            if i == 99:
                raise RuntimeError("provider down")
            return None
        return generate

    def test_failed_beats_reuse_a_neighbour_with_bounded_attempts(self):
        log = []
        with tempfile.TemporaryDirectory() as tmp:
            paths, reused, calls = storyboard.generate_images(["0", "1", "2", "3"], sb_ports(generate_image=self.gen({1, 3}, log)),
                                                              Path(tmp), max_calls=20)
        self.assertEqual(reused, [1, None, 1, None])
        self.assertEqual(paths[0], paths[1])
        self.assertEqual(calls, 2 + 1 + 2 + 1)

    def test_global_call_budget_is_respected(self):
        log = []
        with tempfile.TemporaryDirectory() as tmp:
            paths, reused, calls = storyboard.generate_images(["1", "0", "0", "0"], sb_ports(generate_image=self.gen({1}, log)),
                                                              Path(tmp), max_calls=3)
        self.assertEqual(calls, 3)
        self.assertEqual(len(log), 3)
        self.assertEqual(reused, [None, 0, 0, 0])

    def test_no_picture_at_all_raises(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(RenderError):
            storyboard.generate_images(["99", "0"], sb_ports(generate_image=self.gen(set(), [])), Path(tmp), max_calls=10)

    def test_key_clip_must_stay_in_the_job_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            inside = Path(tmp) / "k.mp4"
            inside.write_bytes(b"x")
            self.assertEqual(storyboard._confined_clip(inside, Path(tmp)), inside.resolve())
            self.assertIsNone(storyboard._confined_clip("/etc/passwd", Path(tmp)))
            self.assertIsNone(storyboard._confined_clip(Path(tmp) / "missing.mp4", Path(tmp)))
            self.assertIsNone(storyboard._confined_clip(None, Path(tmp)))
        self.assertEqual(storyboard.select_key_beats([{"camera": "shake"}, {"section_start": True}, {}], 2), [0, 1])
        self.assertEqual(storyboard.select_key_beats([{}], 0), [])


class StoryboardHarness(Harness):
    """The pipeline with renderer=storyboard; the storyboard render itself is replaced (no ffmpeg, no provider)."""

    def __init__(self, sb=None, outcome_review=(), render_fails=False, **kw):
        super().__init__(**kw)
        self.sb = sb or sb_ports()
        self.events = {}
        self.outcome_review, self.render_fails = list(outcome_review), render_fails

    def ports(self):
        p = super().ports()
        original = p.record_event

        def event(name, **props):
            self.events[name] = props
            original(name, **props)

        p.record_event = event
        p.renderer = "storyboard"
        p.storyboard = self.sb
        p.render = lambda tl, workdir: self.fail_test("the rig renderer must not run")
        return p

    def fail_test(self, msg):
        raise AssertionError(msg)

    def fake_render(self, story, script_, tl, lines, ports, plan, workdir, progress=lambda label: None):
        self.calls.append("storyboard")
        self.lines, self.plan = lines, plan
        if self.render_fails:
            raise RenderError("no picture could be generated for this story")
        rr = RenderResult(Path("silent.mp4"), 1.0, 1.0, 10, 1080, 1920, 25)
        return storyboard.StoryboardOutcome(rr, {"beat_count": 7, "image_count": 6, "images_reused": 1,
                                                  "direction_source": "llm", "caption_style": "bold_stroke"},
                                            self.outcome_review)

    def run(self, s=None):
        with mock.patch.object(storyboard, "render", self.fake_render):
            return super().run(s)


class PipelineWithStoryboard(unittest.TestCase):
    def test_happy_path_events_and_order(self):
        h = StoryboardHarness()
        out = h.run()
        self.assertEqual(out["video_url"], "https://example.test/v1.mp4")
        self.assertLess(h.calls.index("reserve"), h.calls.index("synthesize"))
        self.assertLess(h.calls.index("synthesize"), h.calls.index("storyboard"))
        self.assertLess(h.calls.index("storyboard"), h.calls.index("mix"))
        started, done = h.events["generation_started"], h.events["generation_completed"]
        self.assertEqual(started["renderer"], "storyboard")
        self.assertGreater(started["estimated_cost_usd"], 0)
        self.assertEqual(done["beat_count"], 7)
        self.assertEqual(done["image_count"], 6)
        self.assertEqual(done["renderer"], "storyboard")
        # the measured lines reach the storyboard with alignment, speaker and shot
        self.assertEqual(len(h.lines), len(script()["story"]["shots"]))
        self.assertIn("alignment", h.lines[0])
        self.assertEqual(h.lines[0]["speaker_id"], script()["story"]["shots"][0]["speaker_id"])

    def test_budget_includes_images_and_refuses_before_any_credit(self):
        s = script()
        s["story"]["budget"] = {"max_usd": 0.2}
        h = StoryboardHarness()
        with self.assertRaisesRegex(pipeline.BudgetExceeded, "usd"):
            h.run(s)
        self.assertNotIn("reserve", h.calls)
        self.assertNotIn("synthesize", h.calls)
        self.assertEqual(h.refunds, 0)

    def test_server_cap_refuses_before_any_credit(self):
        h = StoryboardHarness(sb=sb_ports(usd_per_image=5.0, max_usd=8.0))
        with self.assertRaisesRegex(pipeline.BudgetExceeded, "server cap"):
            h.run()
        self.assertNotIn("reserve", h.calls)

    def test_storyboard_needs_no_rig_layout(self):
        s = script()
        s["story"]["characters"][0]["pack_id"] = "rosette_v1"   # refused by rig_v1, fine for pictures
        h = StoryboardHarness()
        h.run(s)
        self.assertIn("publish", h.calls)

    def test_missing_configuration_is_refused_before_credit(self):
        h = StoryboardHarness()
        h.sb = None
        with self.assertRaises(pipeline.AnimationUnavailable):
            h.run()
        self.assertNotIn("reserve", h.calls)

    def test_render_failure_refunds_once(self):
        h = StoryboardHarness(render_fails=True)
        with self.assertRaises(RenderError):
            h.run()
        self.assertEqual(h.refunds, 1)
        self.assertNotIn("publish", h.calls)

    def test_storyboard_review_problems_reach_publication(self):
        problem = quality.Problem("reused_pictures", quality.REVIEW, "x", "y")
        h = StoryboardHarness(outcome_review=[problem])
        out = h.run()
        self.assertTrue(out["needs_review"])
        self.assertEqual(h.published_review, [problem])

    def test_rig_path_is_unchanged_by_default(self):
        h = Harness()
        self.assertEqual(h.ports().renderer, "rig_v1")
        h.run()
        self.assertIn("render", h.calls)


if __name__ == "__main__":
    unittest.main()
