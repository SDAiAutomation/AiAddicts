import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from growthos.engine.story_animation import key_clips as kc

GOOD = {"has_video": True, "duration_s": 4.0, "width": 720, "height": 1280, "black": [], "freeze": []}


def good_measure(_path):
    return dict(GOOD)


class Transport:
    """Fake transport: writes a placeholder file, never touches the network."""

    def __init__(self, fail_times=0, cost=None, error=RuntimeError, sleep_s=0.0, write=True):
        self.calls, self.fail_times, self.cost, self.error, self.sleep_s, self.write = [], fail_times, cost, error, sleep_s, write

    def __call__(self, request, out_path, timeout_s):
        self.calls.append(request)
        if self.sleep_s:
            time.sleep(self.sleep_s)
        if len(self.calls) <= self.fail_times:
            raise self.error("provider exploded")
        if self.write:
            Path(out_path).write_bytes(b"mp4")
        usage = {"seconds": request.duration_s}
        if self.cost is not None:
            usage["cost_usd"] = self.cost
        return usage


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = self.tmp / "clips"

    def beat(self, bid, start, end, intent="", description="", text="", image=True, motion=None):
        path = None
        if image:
            path = self.tmp / f"{bid}.png"
            path.write_bytes(b"png")
        return kc.Beat(id=bid, start=start, end=end, text=text, intent=intent, description=description,
                       image_path=str(path) if path else None, motion=motion)

    def story(self):
        return [
            self.beat("b01", 0, 3, intent="hook", description="the wolf looks at the camera, calm portrait"),
            self.beat("b02", 3, 6, intent="setup", description="a quiet street"),
            self.beat("b03", 6, 9.5, intent="conflict", description="three bosses shake the factory gate"),
            self.beat("b04", 9.5, 12, intent="action", description="the worker walks with a hammer"),
            self.beat("b05", 12, 15, intent="climax", description="the old man throws the contract and jumps"),
            self.beat("b06", 15, 18, intent="resolution", description="the wolf closes the book"),
        ]


class SelectTests(Base):
    def test_picks_motion_beats_in_story_order_and_is_deterministic(self):
        beats = self.story()
        chosen = kc.select_key_beats(beats, max_clips=3)
        self.assertEqual([b.id for b in chosen], ["b03", "b04", "b05"])
        self.assertEqual(chosen, kc.select_key_beats(list(reversed(beats)), max_clips=3))

    def test_explicit_flag_wins_and_false_excludes(self):
        beats = self.story()
        beats[1] = self.beat("b02", 3, 6, description="a quiet street", motion=True)
        beats[4] = self.beat("b05", 12, 15, intent="climax", description="throws and jumps", motion=False)
        ids = [b.id for b in kc.select_key_beats(beats, max_clips=2)]
        self.assertEqual(ids, ["b02", "b03"])

    def test_bounds_and_ineligible_beats(self):
        beats = [
            self.beat("short", 0, 1.0, intent="climax"),
            self.beat("noimg", 1, 4, intent="climax", image=False),
            self.beat("bad id!", 4, 7, intent="climax"),
            self.beat("still", 7, 10, intent="setup", description="a quiet room"),
            self.beat("ok1", 10, 15, intent="climax"),
            self.beat("ok2", 15, 20, intent="conflict"),
        ]
        self.assertEqual([b.id for b in kc.select_key_beats(beats, max_clips=5)], ["ok1", "ok2"])
        self.assertEqual([b.id for b in kc.select_key_beats(beats, max_clips=5, max_total_s=6)], ["ok1"])
        self.assertEqual(kc.select_key_beats(beats, max_clips=0), [])
        self.assertLessEqual(len(kc.select_key_beats(self.story() * 3, max_clips=99)), kc.MAX_CLIPS_LIMIT)

    def test_accepts_dicts(self):
        beat = self.beat("b1", 0, 3, intent="climax")
        chosen = kc.select_key_beats([{"id": "b1", "start": 0, "end": 3, "intent": "climax", "image_path": beat.image_path}])
        self.assertEqual(chosen[0].id, "b1")

    def test_clip_seconds(self):
        self.assertEqual(kc.clip_seconds(kc.Beat("a", 0, 1.6)), 2.0)
        self.assertEqual(kc.clip_seconds(kc.Beat("a", 0, 3.2)), 4.0)
        self.assertEqual(kc.clip_seconds(kc.Beat("a", 0, 9)), kc.MAX_CLIP_S)


class PromptTests(unittest.TestCase):
    def test_prompt_contains_style_identity_accent_no_text_and_camera(self):
        p = kc.build_motion_prompt(kc.Beat("b", 0, 3, intent="climax", description="the old man throws\n the contract"))
        self.assertIn("the old man throws the contract.", p.prompt)
        self.assertIn("rubber hose", p.prompt)
        self.assertIn("single red accent", p.prompt)
        self.assertIn("same design", p.prompt)
        self.assertIn("No text", p.prompt)
        self.assertEqual(p.camera, kc._CAMERA_CLIMAX)
        self.assertEqual(p.version, kc.MOTION_PROMPT_VERSION)
        self.assertNotIn("\n", p.prompt)

    def test_camera_choices_and_fallback_text(self):
        self.assertEqual(kc.build_motion_prompt(kc.Beat("b", 0, 3, description="they run away")).camera, kc._CAMERA_ACTION)
        self.assertEqual(kc.build_motion_prompt(kc.Beat("b", 0, 3, intent="reveal")).camera, kc._CAMERA_REVEAL)
        p = kc.build_motion_prompt(kc.Beat("b", 0, 3, text="Il hésite."))
        self.assertEqual(p.camera, kc._CAMERA_DEFAULT)
        self.assertIn("Il hésite.", p.prompt)
        self.assertLess(len(kc.build_motion_prompt(kc.Beat("b", 0, 3, description="x" * 5000)).prompt), 1200)


class ProviderTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertIsNone(kc.provider_from_env({}))
        self.assertIsNone(kc.provider_from_env({kc.ENV_PROVIDER: "  "}))

    def test_fake_and_unknown_and_stubs(self):
        self.assertIsInstance(kc.provider_from_env({kc.ENV_PROVIDER: "FAKE"}, transport=Transport()), kc.FakeProvider)
        with self.assertRaises(kc.UnknownProvider):
            kc.provider_from_env({kc.ENV_PROVIDER: "sora"})
        for name in ("veo", "seedance", "wan"):
            with self.assertRaises(kc.NotConfigured):
                kc.provider_from_env({kc.ENV_PROVIDER: name})
            self.assertIsNone(kc.PROVIDERS[name].usd_per_second)

    def test_budget_from_env(self):
        b = kc.KeyClipBudget.from_env({})
        self.assertEqual((b.max_usd, b.max_clips, b.max_attempts, b.usd_per_second), (1.5, 4, 2, None))
        b = kc.KeyClipBudget.from_env({kc.ENV_MAX_USD: "abc", kc.ENV_MAX_CLIPS: "50", kc.ENV_USD_PER_S: "0.1"})
        self.assertEqual((b.max_usd, b.max_clips, b.usd_per_second), (1.5, kc.MAX_CLIPS_LIMIT, 0.1))
        self.assertEqual(kc.KeyClipBudget.from_env({kc.ENV_MAX_USD: "9999"}).max_usd, kc.ABSOLUTE_MAX_USD)
        self.assertEqual(kc.KeyClipBudget.from_env({kc.ENV_MAX_USD: "-3"}).max_usd, 1.5)
        self.assertEqual(kc.KeyClipBudget(max_attempts=10).max_attempts, 2)


class ValidationTests(unittest.TestCase):
    def test_good_clip(self):
        self.assertEqual(kc.clip_problems(GOOD, 4.0, 3.5), [])

    def test_rejections(self):
        self.assertEqual(kc.clip_problems({"has_video": False}, 4, 4), ["no_video_stream"])
        self.assertTrue(kc.clip_problems({**GOOD, "duration_s": 2.0}, 4, 4)[0].startswith("too_short"))
        self.assertTrue(kc.clip_problems({**GOOD, "duration_s": 20.0}, 4, 4)[0].startswith("too_long"))
        self.assertTrue(kc.clip_problems({**GOOD, "width": 1280, "height": 720}, 4, 4)[0].startswith("bad_resolution"))
        self.assertTrue(kc.clip_problems({**GOOD, "width": 360, "height": 640}, 4, 4)[0].startswith("bad_resolution"))
        self.assertTrue(kc.clip_problems({**GOOD, "black": [(0, 3)]}, 4, 4)[0].startswith("black"))
        self.assertTrue(kc.clip_problems({**GOOD, "freeze": [(0.5, 3.9)]}, 4, 4)[0].startswith("frozen"))

    def test_longer_clip_than_beat_is_fine(self):
        self.assertEqual(kc.clip_problems({**GOOD, "duration_s": 5.0}, 4.0, 3.2), [])


class MakeKeyClipsTests(Base):
    def run_clips(self, transport, budget=None, beats=None, measure=good_measure, **provider_kw):
        provider = kc.FakeProvider(transport=transport, **provider_kw)
        return kc.make_key_clips(beats or self.story(), provider, budget or kc.KeyClipBudget(max_clips=3),
                                 out_dir=self.out, measure=measure)

    def test_disabled_provider_returns_empty_report(self):
        report = kc.make_key_clips(self.story(), None, out_dir=self.out)
        self.assertEqual(report.clips, {})
        self.assertEqual(report.actual_usd, 0.0)

    def test_success_paths_costs_and_prompt(self):
        t = Transport(cost=0.2)
        report = self.run_clips(t, usd_per_second=0.05)
        self.assertEqual(set(report.clips), {"b03", "b04", "b05"})
        self.assertTrue(all(p is not None and p.is_file() for p in report.clips.values()))
        self.assertEqual(report.estimated_usd, round((4 + 3 + 3) * 0.05, 6))
        self.assertEqual(report.actual_usd, 0.6)
        self.assertEqual(t.calls[0].aspect, "9:16")
        self.assertIn("rubber hose", t.calls[0].prompt)
        d = report.to_dict()
        self.assertEqual(d["version"], kc.KEY_CLIPS_VERSION)
        self.assertEqual(d["prompt_version"], kc.MOTION_PROMPT_VERSION)

    def test_missing_actual_cost_is_unknown_not_zero(self):
        report = self.run_clips(Transport(), usd_per_second=0.05, report_cost=False)
        self.assertIsNone(report.actual_usd)
        self.assertFalse(report.actual_cost_complete)
        self.assertGreater(report.estimated_usd, 0)

    def test_one_retry_then_success(self):
        t = Transport(fail_times=1)
        report = self.run_clips(t, budget=kc.KeyClipBudget(max_clips=1))
        outcome = report.outcomes[0]
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(len(outcome.attempts), 2)
        self.assertIn("provider exploded", outcome.attempts[0].error)

    def test_failure_after_one_retry_keeps_still(self):
        t = Transport(fail_times=99)
        report = self.run_clips(t, budget=kc.KeyClipBudget(max_clips=2))
        self.assertEqual(report.clips, {"b03": None, "b05": None})
        self.assertEqual(len(t.calls), 4)   # 2 beats x (try + one retry)
        self.assertEqual(list(self.out.glob("*.mp4")), [])

    def test_validation_failure_falls_back_and_cleans_file(self):
        report = self.run_clips(Transport(), budget=kc.KeyClipBudget(max_clips=1),
                                measure=lambda p: {**GOOD, "freeze": [(0, 4)]})
        self.assertIsNone(report.clips["b05"])
        self.assertTrue(report.outcomes[0].attempts[0].problems[0].startswith("frozen"))
        self.assertEqual(list(self.out.glob("*.mp4")), [])

    def test_provider_not_writing_file_fails(self):
        report = self.run_clips(Transport(write=False), budget=kc.KeyClipBudget(max_clips=1))
        self.assertEqual(report.outcomes[0].status, "failed")

    def test_measure_crash_falls_back(self):
        def boom(_):
            raise subprocess.CalledProcessError(1, "ffprobe")
        report = self.run_clips(Transport(), budget=kc.KeyClipBudget(max_clips=1), measure=boom)
        self.assertIsNone(report.clips["b05"])

    def test_hard_budget_cap_counts_retries(self):
        # 0.1 $/s, cap 0.5: b03 (4 s) costs 0.40 per attempt; its retry would reach 0.80 -> refused.
        # b05 (3 s) would reach 0.40 + 0.30 = 0.70 -> skipped before any call.
        t = Transport(fail_times=99)
        report = self.run_clips(t, budget=kc.KeyClipBudget(max_clips=2, max_usd=0.5), usd_per_second=0.1)
        self.assertEqual(len(t.calls), 1)
        statuses = {o.beat_id: o.status for o in report.outcomes}
        self.assertEqual(statuses, {"b03": "failed", "b05": "skipped_budget"})
        self.assertLessEqual(report.estimated_usd, 0.5)

    def test_rate_override_and_unknown_rate(self):
        t = Transport()
        report = self.run_clips(t, usd_per_second=None)
        self.assertEqual(t.calls, [])
        self.assertTrue(all(o.status == "rate_unknown" for o in report.outcomes))
        report = self.run_clips(Transport(), budget=kc.KeyClipBudget(max_clips=1, usd_per_second=0.2), usd_per_second=None)
        self.assertEqual(report.outcomes[0].status, "ok")
        self.assertAlmostEqual(report.estimated_usd, 0.6)

    def test_timeout_is_bounded_and_falls_back(self):
        t = Transport(sleep_s=1.5)
        started = time.monotonic()
        report = self.run_clips(t, budget=kc.KeyClipBudget(max_clips=1, timeout_s=1.0, max_attempts=1))
        self.assertLess(time.monotonic() - started, 1.45)
        self.assertIn("timeout", report.outcomes[0].attempts[0].error)
        self.assertIsNone(report.clips["b05"])

    def test_not_configured_mid_run_stops_everything(self):
        report = self.run_clips(Transport(fail_times=99, error=kc.NotConfigured))
        self.assertEqual([o.status for o in report.outcomes], ["not_configured"] * 3)
        self.assertEqual(len(report.outcomes[0].attempts) + len(report.outcomes[1].attempts), 1)

    def test_image_root_and_suffix_validation(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "x.png").write_bytes(b"png")
        (self.tmp / "y.txt").write_text("nope")
        beats = [kc.Beat("a1", 0, 3, intent="climax", image_path=str(outside / "x.png")),
                 kc.Beat("a2", 3, 6, intent="climax", image_path=str(self.tmp / "y.txt")),
                 kc.Beat("a3", 6, 9, intent="climax", image_path=str(self.tmp / ".." / outside.name / "x.png"))]
        t = Transport()
        report = kc.make_key_clips(beats, kc.FakeProvider(transport=t), kc.KeyClipBudget(), out_dir=self.out,
                                   image_root=self.tmp, measure=good_measure)
        self.assertEqual([o.status for o in report.outcomes], ["skipped_invalid"] * 3)
        self.assertEqual(t.calls, [])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
class FfmpegIntegrationTests(Base):
    def test_fake_local_provider_produces_a_valid_clip(self):
        image = self.tmp / "still.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=540x960:d=1",
                        "-frames:v", "1", str(image)], check=True)
        beat = kc.Beat("k1", 0, 2.0, intent="climax", image_path=str(image))
        report = kc.make_key_clips([beat], kc.FakeProvider(), kc.KeyClipBudget(), out_dir=self.out)
        self.assertEqual(report.outcomes[0].status, "ok", report.to_dict())
        self.assertEqual(report.actual_usd, 0.0)
        m = kc.measure_clip(report.clips["k1"])
        self.assertEqual((m["width"], m["height"]), (540, 960))

    def test_black_still_is_rejected(self):
        image = self.tmp / "black.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=540x960",
                        "-frames:v", "1", str(image)], check=True)
        beat = kc.Beat("k2", 0, 2.0, intent="climax", image_path=str(image))
        report = kc.make_key_clips([beat], kc.FakeProvider(), kc.KeyClipBudget(), out_dir=self.out)
        self.assertIsNone(report.clips["k2"])
        self.assertTrue(any(p.startswith("black") for p in report.outcomes[0].attempts[0].problems))


if __name__ == "__main__":
    unittest.main()
