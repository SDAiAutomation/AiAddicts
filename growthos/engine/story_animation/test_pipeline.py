import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from growthos.engine.story_animation import pipeline
from growthos.engine.story_animation.test_timeline_lib import alignment, loud

FIXTURE = Path(__file__).parent / "fixtures" / "rig_v1_story.json"


def script():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class Harness:
    """Fake ports that record calls; `fail` names the stage that raises."""

    def __init__(self, fail=None, reserve=True, ready=None, quality=None, refund_raises=False, event_raises=False, progress_raises=False):
        self.calls, self.fail, self.refunds = [], fail, 0
        self.progress_raises = progress_raises
        self.reserve, self.ready_problems, self.quality_problems = reserve, ready or [], quality or []
        self.refund_raises, self.event_raises = refund_raises, event_raises

    def step(self, name, value=None):
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError(f"{name} broke")
        return value

    def ports(self):
        def refund():
            self.calls.append("refund")
            self.refunds += 1
            if self.refund_raises:
                raise RuntimeError("refund broke")

        def event(name, **props):
            self.calls.append("event:" + name)
            if self.event_raises and name == "generation_completed":
                raise RuntimeError("event broke")

        def synth(text, voice, wav):
            self.calls.append("synthesize")
            if self.fail == "synthesize" and self.calls.count("synthesize") == 3:
                raise RuntimeError("synthesize broke")
            n = 20
            return {"duration_s": 2.0, "alignment": alignment("a" * n, 0.1), "envelope": loud(48)}

        return pipeline.Ports(
            authorize=lambda: self.step("authorize"),
            moderate=lambda s: self.step("moderate"),
            ready=lambda: (self.calls.append("ready"), self.ready_problems)[1],
            estimate=lambda seconds, chars: SimpleNamespace(render_seconds=seconds * 4, tts_chars=chars),
            reserve_credit=lambda: (self.calls.append("reserve"), self.reserve)[1],
            refund_credit=refund,
            record_event=event,
            synthesize=synth,
            render=lambda tl, workdir: self.step("render", SimpleNamespace(video_path=Path("silent.mp4"))),
            mix=lambda rendered, starts, tl, out: self.step("mix", Path("final.mp4")),
            check_quality=lambda final: (self.calls.append("quality"), self.quality_problems)[1],
            publish=lambda final, tl: self.step("publish", {"video_url": "https://example.test/v1.mp4", "content_item_id": "item"}),
            catalog=pipeline.RIG_V1_CATALOG,
            progress=self.on_progress,
        )

    def on_progress(self, label):
        self.calls.append("progress:" + label)
        if self.progress_raises:
            raise RuntimeError("progress broke")

    def run(self, s=None):
        return pipeline.run(s or script(), self.ports(), Path("unused-workdir"))


class RefusalsHappenBeforeAnyCredit(unittest.TestCase):
    def assertNoMoney(self, h):
        self.assertNotIn("reserve", h.calls)
        self.assertNotIn("synthesize", h.calls)
        self.assertEqual(h.refunds, 0)

    def test_invalid_contract(self):
        h, s = Harness(), script()
        s["story"]["shots"][0]["actors"][0]["mood"] = "furious"
        with self.assertRaises(ValueError):
            h.run(s)
        self.assertNoMoney(h)
        self.assertEqual(h.calls, [])

    def test_missing_story(self):
        h = Harness()
        with self.assertRaises(ValueError):
            pipeline.run({"content_format": "story"}, h.ports(), Path("x"))
        self.assertNoMoney(h)

    def test_two_characters_on_the_same_rig_are_refused(self):
        h, s = Harness(), script()
        s["story"]["characters"][0]["pack_id"] = "rosette_v1"  # both characters would be drawn as the same rig
        with self.assertRaisesRegex(pipeline.AnimationUnavailable, "both use"):
            h.run(s)
        self.assertNoMoney(h)

    def test_a_pack_outside_the_catalog_is_refused_by_the_contract(self):
        h, s = Harness(), script()
        s["story"]["characters"][0]["pack_id"] = "other_account_pack"
        with self.assertRaises(ValueError):
            h.run(s)
        self.assertNoMoney(h)

    def test_any_number_of_shots_is_accepted(self):
        for count in (1, 3, 4):
            h, s = Harness(), script()
            s["story"]["shots"] = s["story"]["shots"][:count]
            captured = {}
            ports = h.ports()
            ports.render = lambda tl, workdir: captured.update(tl) or SimpleNamespace(video_path=Path("s.mp4"))
            with self.subTest(count=count):
                pipeline.run(s, ports, Path("x"))
                self.assertEqual(len(captured["shots"]), count)
                self.assertEqual(h.calls.count("synthesize"), count)
                self.assertEqual(h.refunds, 0)

    def test_authorization_denied(self):
        h = Harness(fail="authorize")
        with self.assertRaises(RuntimeError):
            h.run()
        self.assertNoMoney(h)
        self.assertNotIn("moderate", h.calls)

    def test_moderation_refused(self):
        h = Harness(fail="moderate")
        with self.assertRaises(RuntimeError):
            h.run()
        self.assertNoMoney(h)

    def test_worker_not_ready(self):
        h = Harness(ready=["GODOT_BIN is not set"])
        with self.assertRaisesRegex(pipeline.AnimationUnavailable, "GODOT_BIN"):
            h.run()
        self.assertNoMoney(h)

    def test_budget_exceeded(self):
        for key, value in (("max_tts_chars", 10), ("max_render_s", 5), ("max_usd", 0.001)):
            h, s = Harness(), script()
            s["story"]["budget"] = {key: value}
            with self.subTest(key), self.assertRaises(pipeline.BudgetExceeded):
                h.run(s)
            self.assertNoMoney(h)

    def test_no_credit_available(self):
        h = Harness(reserve=False)
        with self.assertRaises(pipeline.InsufficientCredits):
            h.run()
        self.assertEqual(h.refunds, 0)
        self.assertNotIn("synthesize", h.calls)
        self.assertNotIn("event:generation_started", h.calls)


class FailuresAfterReservationRefundExactlyOnce(unittest.TestCase):
    def test_each_stage(self):
        for stage in ("synthesize", "render", "mix", "publish"):
            h = Harness(fail=stage)
            with self.subTest(stage), self.assertRaisesRegex(RuntimeError, f"{stage} broke"):
                h.run()
            self.assertEqual(h.refunds, 1, h.calls)
            self.assertLess(h.calls.index("reserve"), h.calls.index("refund"))
            self.assertNotIn("event:generation_completed", h.calls)

    def test_quality_rejection_refunds(self):
        h = Harness(quality=["black frames between 5s and 6s"])
        with self.assertRaises(pipeline.QualityRejected):
            h.run()
        self.assertEqual(h.refunds, 1)
        self.assertNotIn("publish", h.calls)

    def test_invalid_measured_duration_refunds(self):
        h, p = Harness(), None
        ports = h.ports()
        ports.synthesize = lambda text, voice, wav: {"duration_s": 0, "alignment": alignment("aa"), "envelope": loud(4)}
        with self.assertRaises(ValueError):
            pipeline.run(script(), ports, Path("x"))
        self.assertEqual(h.refunds, 1)

    def test_a_failing_refund_does_not_hide_the_cause(self):
        h = Harness(fail="render", refund_raises=True)
        with self.assertRaisesRegex(RuntimeError, "render broke"):
            h.run()
        self.assertEqual(h.refunds, 1)


class SuccessPath(unittest.TestCase):
    def test_order_and_no_refund(self):
        h = Harness()
        result = h.run()
        self.assertEqual(h.refunds, 0)
        self.assertEqual(result["video_url"], "https://example.test/v1.mp4")
        order = [c for c in h.calls if c in ("authorize", "moderate", "ready", "reserve", "render", "mix", "quality", "publish")]
        self.assertEqual(order, ["authorize", "moderate", "ready", "reserve", "render", "mix", "quality", "publish"])
        self.assertEqual(h.calls.count("synthesize"), 6)
        self.assertEqual(h.calls.count("reserve"), 1)

    def test_bookkeeping_error_after_publication_is_not_a_failure(self):
        h = Harness(event_raises=True)
        result = h.run()
        self.assertEqual(h.refunds, 0)
        self.assertTrue(result["video_url"])

    def test_progress_labels_follow_the_stages(self):
        h = Harness()
        h.run()
        labels = [c for c in h.calls if c.startswith("progress:")]
        self.assertEqual(labels, ["progress:Voix des personnages", "progress:Animation", "progress:Mixage audio",
                                  "progress:Contrôle qualité", "progress:Publication"])

    def test_a_failing_progress_report_never_fails_or_refunds_the_job(self):
        h = Harness(progress_raises=True)
        result = h.run()
        self.assertEqual(h.refunds, 0)
        self.assertTrue(result["video_url"])

    def test_timeline_has_what_the_scene_needs(self):
        captured = {}
        h = Harness()
        ports = h.ports()
        ports.render = lambda tl, workdir: captured.update(tl) or SimpleNamespace(video_path=Path("s.mp4"))
        pipeline.run(script(), ports, Path("x"))
        for key in ("fps", "total", "lines", "subs", "shots"):
            self.assertIn(key, captured)
        self.assertEqual([l["who"] for l in captured["lines"]], ["ros", "pip", "ros", "pip", "ros", "pip"])
        self.assertEqual([s["speaker"] for s in captured["shots"]], [l["who"] for l in captured["lines"]])
        self.assertEqual(captured["shots"][0]["start"], 0.0)
        self.assertEqual(captured["shots"][-1]["end"], captured["total"])

    def test_estimates_are_conservative_numbers(self):
        self.assertAlmostEqual(pipeline.estimated_video_seconds(280), 280 / 14 + 3.1)


if __name__ == "__main__":
    unittest.main()
