"""Worker routing of illustrated stories: flag OFF refuses before any credit, legacy scripts never change route, and the real
`assembler.run_for_content_item -> _run_visual -> story_visual.pipeline.run` wiring refuses a non-administrator before moderation or credit.
No network, no key, no paid provider (the providers are stubbed)."""
import os
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from engine import assembler
from engine.explainer import access as explainer_access
from engine.story_visual import contract, pipeline, sample

VOICE = "voiceid12345678"
RATES = {"STORY_IMAGE_USD_EACH": "0.08", "ELEVENLABS_USD_PER_1K_CHARS": "0.18", "SCRIPT_PRICE_IN_PER_M": "1", "SCRIPT_PRICE_OUT_PER_M": "4",
         "STORY_PLAN_TOKENS_IN": "4000", "STORY_PLAN_TOKENS_OUT": "3500", "STORY_RENDER_USD": "0", "STORY_STORAGE_USD": "0.01"}
STANDARD = {"title": "t", "niche": "n", "account": "a", "platform": "tiktok", "blocks": [{"role": "hook", "text": "Bonjour"}]}


def visual_script():
    plan = sample.moral_plan()
    plan["voice_id"] = VOICE
    return {"content_format": "story_visual", "story_plan": plan}


class Harness(unittest.TestCase):
    def start(self, script, flag=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {}))
        os.environ.pop("STORY_VISUAL_ENABLED", None)
        if flag is not None:
            os.environ["STORY_VISUAL_ENABLED"] = flag
        stack.enter_context(patch("engine.assembler.db.get_service_client", return_value=Mock()))
        stack.enter_context(patch("engine.assembler.repo.get_script", return_value=script))
        self.reserve = stack.enter_context(patch("engine.assembler.repo.reserve_generation_credit", return_value=True))
        self.refund = stack.enter_context(patch("engine.assembler.repo.refund_generation_credit"))
        self.normalize = stack.enter_context(patch("engine.assembler.script_module.normalize_script", side_effect=RuntimeError("legacy path reached")))
        self.moderation = stack.enter_context(patch("engine.assembler.moderation.check_script"))
        stack.enter_context(patch("engine.assembler.moderation.check_integrity"))
        stack.enter_context(patch("engine.assembler.events.organization_id_of", return_value="org"))
        stack.enter_context(patch("engine.assembler.events.record"))
        stack.enter_context(patch("engine.assembler.repo.update_content_item"))
        self.stack = stack


class FlagOff(Harness):
    def test_visual_story_is_refused_before_anything_happens(self):
        for value in (None, "", "0", "false", "no"):
            with self.subTest(flag=value):
                self.start(visual_script(), flag=value)
                with self.assertRaises(contract.VisualDisabled):
                    assembler.run_for_content_item("item")
                self.reserve.assert_not_called()
                self.moderation.assert_not_called()
                self.normalize.assert_not_called()


class LegacyPathsNeverChange(Harness):
    SCRIPTS = {
        "standard": STANDARD,
        "quiz": {"content_format": "quiz", "title": "q"},
        "story v1": {"content_format": "story", "story": {"version": 1, "target_duration_s": 3, "characters": [], "shots": []}},
    }

    def test_legacy_scripts_reach_normalisation_whatever_the_flag(self):
        for name, script in self.SCRIPTS.items():
            for flag in (None, "1", "0"):
                with self.subTest(script=name, flag=flag):
                    self.start(script, flag=flag)
                    with self.assertRaisesRegex(RuntimeError, "legacy path reached"):
                        assembler.run_for_content_item("item")
                    self.reserve.assert_not_called()


class RealWiringRefusesANonAdministratorFirst(Harness):
    """Flag ON, real `_run_visual` and real `pipeline.run`: the platform-administrator check comes before moderation and credit."""

    def test_non_administrator_is_refused_before_moderation_and_credit(self):
        self.start(visual_script(), flag="1")
        # NO rates configured on purpose: the administrator check must come first, so a refused caller never even reaches the cost check
        configure = self.stack.enter_context(patch("engine.assembler.asset_store.configure"))
        denied = self.stack.enter_context(patch("engine.assembler.explainer_access.authorize", side_effect=explainer_access.ExplainerAccessDenied("no")))
        images = self.stack.enter_context(patch("engine.story_visual.orchestrator.openai_provider", return_value=Mock()))
        voices = self.stack.enter_context(patch("engine.story_visual.voice.elevenlabs_provider", return_value=Mock()))
        with self.assertRaisesRegex(pipeline.PipelineError, "administrateurs"):
            assembler.run_for_content_item("item", "output")
        denied.assert_called_once()
        configure.assert_not_called()  # a refused caller never reaches the shared asset cache
        self.moderation.assert_not_called()  # authorization first: a non-administrator costs not even a moderation call
        self.reserve.assert_not_called()
        self.refund.assert_not_called()
        for provider in (images.return_value, voices.return_value):
            provider.assert_not_called()
        self.normalize.assert_not_called()


class WiringOfTheOperationalGuards(Harness):
    """Administrator allowed, rates configured: the shared quota (read from the database, fail-closed) stops the job before any credit or
    provider call, and the asset cache is configured after authorization and always released."""

    def test_a_refused_quota_stops_before_credit_and_providers(self):
        self.start(visual_script(), flag="1")
        self.stack.enter_context(patch.dict(os.environ, RATES))
        self.stack.enter_context(patch("engine.assembler.explainer_access.authorize"))
        configure = self.stack.enter_context(patch("engine.assembler.asset_store.configure"))
        reset = self.stack.enter_context(patch("engine.assembler.asset_store.reset"))
        self.stack.enter_context(patch("engine.story_visual.quota.SharedQuota.consume", return_value=False))
        images = self.stack.enter_context(patch("engine.story_visual.orchestrator.openai_provider", return_value=Mock()))
        voices = self.stack.enter_context(patch("engine.story_visual.voice.elevenlabs_provider", return_value=Mock()))
        with self.assertRaisesRegex(pipeline.PipelineError, "quota"):
            assembler.run_for_content_item("item", "output")
        configure.assert_called_once()
        reset.assert_called_once()
        self.reserve.assert_not_called()
        for provider in (images.return_value, voices.return_value):
            provider.assert_not_called()

    def test_the_daily_limit_is_configurable_and_never_negative(self):
        for value, expected in ((None, 3), ("", 3), ("5", 5), ("0", 0), ("-2", 0), ("x", 3)):
            with self.subTest(value=value), patch.dict(os.environ, {} if value is None else {"STORY_VISUAL_MAX_JOBS_PER_DAY": value}):
                if value is None:
                    os.environ.pop("STORY_VISUAL_MAX_JOBS_PER_DAY", None)
                self.assertEqual(assembler._story_visual_daily_jobs(), expected)


if __name__ == "__main__":
    unittest.main()
