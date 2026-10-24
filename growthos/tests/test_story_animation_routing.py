"""Routing of animated stories in the worker: flag OFF refuses before any credit, legacy scripts never change route."""
import json
import os
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import worker
from engine import assembler
from engine.story_animation import contract, pipeline

FIXTURE = Path(__file__).resolve().parents[1] / "engine" / "story_animation" / "fixtures" / "rig_v1_story.json"
STANDARD = {"title": "t", "niche": "n", "account": "a", "platform": "tiktok", "blocks": [{"role": "hook", "text": "Bonjour"}]}


def animated_script():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class Harness(unittest.TestCase):
    def start(self, script, flag=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        env = {} if flag is None else {"STORY_ANIMATION_ENABLED": flag}
        stack.enter_context(patch.dict(os.environ, env))
        if flag is None:
            os.environ.pop("STORY_ANIMATION_ENABLED", None)
        stack.enter_context(patch("engine.assembler.db.get_service_client", return_value=Mock()))
        stack.enter_context(patch("engine.assembler.repo.get_script", return_value=script))
        self.reserve = stack.enter_context(patch("engine.assembler.repo.reserve_generation_credit", return_value=True))
        self.refund = stack.enter_context(patch("engine.assembler.repo.refund_generation_credit"))
        self.animated = stack.enter_context(patch("engine.assembler._run_animated", return_value={"video_url": "u"}))
        self.normalize = stack.enter_context(patch("engine.assembler.script_module.normalize_script", side_effect=RuntimeError("legacy path reached")))
        stack.enter_context(patch("engine.assembler.moderation.check_script"))
        stack.enter_context(patch("engine.assembler.moderation.check_integrity"))
        stack.enter_context(patch("engine.assembler.events.organization_id_of", return_value="org"))
        stack.enter_context(patch("engine.assembler.events.record"))


class FlagOff(Harness):
    def test_animated_story_is_refused_before_anything_happens(self):
        self.start(animated_script())
        with self.assertRaises(contract.AnimationDisabled):
            assembler.run_for_content_item("item")
        self.animated.assert_not_called()
        self.reserve.assert_not_called()
        self.refund.assert_not_called()
        self.normalize.assert_not_called()

    def test_explicit_false_values_keep_it_off(self):
        for value in ("0", "false", "", "no"):
            with self.subTest(value):
                self.start(animated_script(), flag=value)
                with self.assertRaises(contract.AnimationDisabled):
                    assembler.run_for_content_item("item")
                self.reserve.assert_not_called()


class FlagOn(Harness):
    def test_animated_story_goes_to_its_own_pipeline(self):
        self.start(animated_script(), flag="1")
        self.assertEqual(assembler.run_for_content_item("item", "out"), {"video_url": "u"})
        self.animated.assert_called_once()
        self.assertEqual(self.animated.call_args.args[1], "item")
        self.normalize.assert_not_called()
        self.reserve.assert_not_called()  # reservation belongs to the pipeline, after the refusals


class LegacyPathsNeverChange(Harness):
    SCRIPTS = {
        "standard": STANDARD,
        "story v1": {"content_format": "story", "story": {"version": 1, "target_duration_s": 3, "characters": [], "shots": []}},
        "quiz": {"content_format": "quiz", "title": "q"},
    }

    def test_legacy_scripts_reach_normalisation_whatever_the_flag(self):
        for name, script in self.SCRIPTS.items():
            for flag in (None, "1", "0"):
                with self.subTest(script=name, flag=flag):
                    self.start(script, flag=flag)
                    with self.assertRaisesRegex(RuntimeError, "legacy path reached"):
                        assembler.run_for_content_item("item")
                    self.animated.assert_not_called()
                    self.reserve.assert_not_called()  # normalisation failed first, exactly as before this change


class AnimatedWiringRefusesBeforeCredit(unittest.TestCase):
    """`_run_animated` with the flag ON but a worker that is not configured for Godot: refused, nothing reserved."""

    def test_unconfigured_worker(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"STORY_ANIMATION_ENABLED": "1"}))
            os.environ.pop("GODOT_BIN", None)
            os.environ.pop("STORY_PACK_DIR", None)
            reserve = stack.enter_context(patch("engine.assembler.repo.reserve_generation_credit", return_value=True))
            stack.enter_context(patch("engine.assembler.explainer_access.authorize"))
            stack.enter_context(patch("engine.assembler.moderation.check_script"))
            stack.enter_context(patch("engine.assembler.events.organization_id_of", return_value="org"))
            events = stack.enter_context(patch("engine.assembler.events.record"))
            with self.assertRaisesRegex(pipeline.AnimationUnavailable, "GODOT_BIN"):
                assembler._run_animated(Mock(), "item", animated_script(), "out", 0.0)
            reserve.assert_not_called()
            events.assert_not_called()

    def test_non_admin_author_is_refused_before_credit(self):
        from engine.explainer import access
        with ExitStack() as stack:
            reserve = stack.enter_context(patch("engine.assembler.repo.reserve_generation_credit", return_value=True))
            stack.enter_context(patch("engine.assembler.explainer_access.authorize", side_effect=access.ExplainerAccessDenied("no")))
            stack.enter_context(patch("engine.assembler.events.organization_id_of", return_value="org"))
            with self.assertRaisesRegex(pipeline.AnimationError, "administrateurs"):
                assembler._run_animated(Mock(), "item", animated_script(), "out", 0.0)
            reserve.assert_not_called()


class HeartbeatKeepsLongRendersAlive(unittest.TestCase):
    """repo.reclaim_stale_generating_items re-queues items idle for 15 minutes: a long render must keep touching the row."""

    def run_with(self, update_side_effect=None):
        import threading
        import time
        with ExitStack() as stack:
            stack.enter_context(patch("engine.assembler._ANIMATION_HEARTBEAT_S", 0.03))
            update = stack.enter_context(patch("engine.assembler.repo.update_content_item", side_effect=update_side_effect))
            stack.enter_context(patch("engine.assembler.events.organization_id_of", return_value="org"))
            stack.enter_context(patch("engine.story_animation.pipeline.run", side_effect=lambda *a, **k: time.sleep(0.3) or {"video_url": "u"}))
            result = assembler._run_animated(Mock(), "item", animated_script(), "out", 0.0)
        self.assertEqual(result, {"video_url": "u"})
        self.assertFalse(any(t.name == "animation-heartbeat" for t in threading.enumerate()))
        return update

    def test_item_is_touched_repeatedly_and_the_thread_stops(self):
        update = self.run_with()
        self.assertGreaterEqual(update.call_count, 3)

    def test_a_failing_heartbeat_never_fails_the_job(self):
        update = self.run_with(update_side_effect=RuntimeError("db blip"))
        self.assertGreaterEqual(update.call_count, 1)


class WorkerFailureRecording(unittest.TestCase):
    def test_flag_off_marks_the_job_failed_without_touching_credits(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {}))
            os.environ.pop("STORY_ANIMATION_ENABLED", None)
            stack.enter_context(patch("worker.process_trim", return_value=False))
            stack.enter_context(patch("worker.repo.claim_queued_item", return_value={"id": "item"}))
            failed = stack.enter_context(patch("worker.repo.mark_failed"))
            stack.enter_context(patch("worker.events.record"))
            stack.enter_context(patch("worker.events.organization_id_of", return_value="org"))
            stack.enter_context(patch("engine.assembler.db.get_service_client", return_value=Mock()))
            stack.enter_context(patch("engine.assembler.repo.get_script", return_value=animated_script()))
            reserve = stack.enter_context(patch("engine.assembler.repo.reserve_generation_credit"))
            refund = stack.enter_context(patch("engine.assembler.repo.refund_generation_credit"))
            self.assertTrue(worker.process_one(Mock()))
            failed.assert_called_once()
            self.assertIn("not enabled", failed.call_args.args[2])
            reserve.assert_not_called()
            refund.assert_not_called()


if __name__ == "__main__":
    unittest.main()
