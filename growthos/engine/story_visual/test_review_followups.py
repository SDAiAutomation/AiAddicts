"""Suites de la revue de #103 : remboursement (règle A), reprise d'une image disparue, statut de revue, nature des coûts, garde de durée.
Doublures uniquement : aucun réseau, aucun fournisseur payant."""
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from growthos.engine import tts
from growthos.engine.story_visual.cost import BudgetExceeded
from growthos.engine.story_visual import cost, ledger, orchestrator, pipeline, render, sample, voice
from growthos.engine.story_visual.test_ledger import FakeDb, ITEM
from growthos.engine.story_visual.test_pipeline import Harness, Tmp, VOICE

needs_ffmpeg = unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")


class PaidImages(sample.PlaceholderImageProvider):
    """Doublure qui déclare un coût réel non nul (aucun appel payant)."""
    def __call__(self, *a, **k):
        result = super().__call__(*a, **k)
        if result.path:
            result.cost_usd = 0.05
        return result


@needs_ffmpeg
class TestRefundRuleA(Harness):
    def test_refund_when_nothing_was_spent(self):
        with patch.object(pipeline.render, "render_story", side_effect=pipeline.render.RenderError("boom")):
            with self.assertRaises(pipeline.render.RenderError):
                self.run_pipeline()
        self.assertEqual(self.refunds, [1])  # doublures à 0 $ mesuré : aucune dépense

    def test_no_refund_when_money_was_spent(self):
        with patch.object(pipeline.render, "render_story", side_effect=pipeline.render.RenderError("boom")):
            with self.assertRaises(pipeline.render.RenderError):
                self.run_pipeline(image_provider=PaidImages())
        self.assertEqual(self.refunds, [])

    def test_no_refund_when_a_failed_call_has_an_unknown_cost(self):
        provider = sample.PlaceholderImageProvider()
        provider.fail_next = 1
        with self.assertRaises(pipeline.PipelineError):
            self.run_pipeline(image_provider=provider)
        self.assertEqual(self.refunds, [])

    def test_no_refund_after_a_successful_publication_and_the_error_is_not_masked(self):
        def events(name, **props):
            if name == "generation_completed":
                raise RuntimeError("event store down")
        with self.assertRaisesRegex(RuntimeError, "event store down"):
            self.run_pipeline(publish=lambda v, t, r: {"video_url": "x"}, record_event=events)
        self.assertEqual(self.refunds, [])

class TestRefundWhenNothingWasSpent(Harness):
    """Règle A, cas « rien dépensé » : tout échec AVANT le premier appel payant rend le crédit, exactement une fois."""

    def test_failure_right_after_the_credit_reservation_refunds_once(self):
        def events(name, **props):
            if name == "generation_started":
                raise RuntimeError("event store down")
        provider = sample.PlaceholderImageProvider()
        with self.assertRaisesRegex(RuntimeError, "event store down"):
            self.run_pipeline(image_provider=provider, record_event=events)
        self.assertEqual(provider.calls, [])  # aucun appel payant n'a eu lieu
        self.assertEqual(self.refunds, [1])

    def test_refused_paid_call_before_any_provider_call_refunds_once(self):
        led = ledger.DurableLedger(FakeDb(), ITEM, 0.01)  # plafond restant > 0 mais < coût d'une image : la retenue est refusée
        provider = sample.PlaceholderImageProvider()
        with self.assertRaises(BudgetExceeded):
            self.run_pipeline(image_provider=provider, ledger=led)
        self.assertEqual(provider.calls, [])
        self.assertEqual(self.refunds, [1])

    def test_failure_before_the_credit_reservation_never_refunds(self):
        def refuse(script):
            raise RuntimeError("moderation refused")
        with self.assertRaisesRegex(RuntimeError, "moderation refused"):
            self.run_pipeline(moderate=refuse)
        self.assertEqual(self.refunds, [])  # le crédit n'avait pas été pris


class TestResumeWithDurableLedger(Tmp):
    def test_vanished_done_scene_is_resumed_without_error_and_without_double_counting_the_settled_row(self):
        db = FakeDb()
        plan = sample.moral_plan()
        kw = dict(tenant_id="t", work_dir=self.tmp, expected_unit_usd=0.05, max_scene_regenerations=0, max_story_regenerations=0)
        first_ledger = ledger.DurableLedger(db, ITEM, 10)
        provider = sample.PlaceholderImageProvider()
        first = orchestrator.generate_scene_images(
            plan, provider=provider, tracker=cost.BudgetTracker(cost.Budget(max_usd=10), ledger=first_ledger), **kw)
        rows_before = [dict(r) for r in db.rows]
        self.assertEqual(len(rows_before), 8)
        Path(first["s1"]["path"]).unlink()
        # nouveau coureur, nouveau registre (mémoire vide) sur la même base durable : reprise de l'item image:s1 déjà réglé
        tracker = cost.BudgetTracker(cost.Budget(max_usd=10), ledger=ledger.DurableLedger(db, ITEM, 10))
        again = orchestrator.generate_scene_images(plan, provider=provider, tracker=tracker, **kw)
        self.assertEqual(again["s1"]["status"], "done")
        self.assertEqual(again["s1"]["generations"], 1)
        self.assertTrue(Path(again["s1"]["path"]).is_file())
        self.assertEqual(len(provider.calls), 9)  # une seule image refaite
        # les 8 lignes réglées d'origine sont intactes ; la reprise ajoute UNE retenue pour l'image réellement refaite
        self.assertEqual(db.rows[:8], rows_before)
        self.assertEqual(len(db.rows), 9)
        self.assertEqual(db.rows[8]["provider"], "ledger:settled:image:s1")
        self.assertTrue(all(":reserved:" not in r["provider"] for r in db.rows))  # aucune retenue orpheline
        self.assertEqual(tracker.holds, {})

    def test_same_runner_resume_does_not_raise_on_an_already_settled_item(self):
        db = FakeDb()
        plan = sample.moral_plan()
        kw = dict(tenant_id="t", work_dir=self.tmp, expected_unit_usd=0.05, max_scene_regenerations=0, max_story_regenerations=0)
        led = ledger.DurableLedger(db, ITEM, 10)
        provider = sample.PlaceholderImageProvider()
        tracker = cost.BudgetTracker(cost.Budget(max_usd=10), ledger=led)
        first = orchestrator.generate_scene_images(plan, provider=provider, tracker=tracker, **kw)
        Path(first["s1"]["path"]).unlink()
        again = orchestrator.generate_scene_images(plan, provider=provider, tracker=tracker, **kw)  # même tracker, même registre
        self.assertEqual(again["s1"]["status"], "done")
        led.settle("image:s1", 0.05)  # un règlement en double d'un item déjà réglé est sans effet et ne lève pas
        led.settle("image:s1", None)
        self.assertEqual(sum(1 for r in db.rows if r["provider"].endswith("image:s1")), 2)


class TestMissingImageIsAResume(Tmp):
    def test_done_scene_whose_file_vanished_is_regenerated_without_counting(self):
        plan = sample.moral_plan()
        kw = dict(tenant_id="t", work_dir=self.tmp, expected_unit_usd=0.05, max_scene_regenerations=0, max_story_regenerations=0)
        provider = sample.PlaceholderImageProvider()
        first = orchestrator.generate_scene_images(plan, provider=provider, tracker=cost.BudgetTracker(cost.Budget()), **kw)
        Path(first["s1"]["path"]).unlink()
        again = orchestrator.generate_scene_images(plan, provider=provider, tracker=cost.BudgetTracker(cost.Budget()), **kw)
        self.assertEqual(again["s1"]["status"], "done")
        self.assertEqual(again["s1"]["generations"], 1)
        self.assertEqual(len(provider.calls), 9)


class TestReviewStatus(unittest.TestCase):
    def test_unreadable_text_is_delivered_as_quality_check(self):
        fields = pipeline.review_fields({"review": ["s2: text not readable (fits=False, contrast=2.0)"]})
        self.assertEqual(fields["status"], "quality_check")
        self.assertEqual(len(fields["quality_flags"]), 1)

    def test_clean_result_is_a_plain_video(self):
        self.assertEqual(pipeline.review_fields({"review": []}), {"status": "video", "quality_flags": []})


class TestCostKinds(Tmp):
    def test_table_price_is_estimated_and_usage_price_is_measured(self):
        out = str(self.tmp / "a.png")
        with patch.object(orchestrator.openai_images, "generate_image", return_value=out), \
                patch.object(orchestrator.openai_images, "pop_last_usage", return_value=None), \
                patch.dict("os.environ", {}, clear=True):
            table = orchestrator.openai_provider()("p", out, model="gpt-image-1", quality="high")
        self.assertEqual((table.cost_usd, table.cost_kind), (0.19, cost.ESTIMATED))
        usage = {"input_text": 0, "input_image": 0, "output": 1000}
        with patch.object(orchestrator.openai_images, "generate_image", return_value=out), \
                patch.object(orchestrator.openai_images, "pop_last_usage", return_value=usage), \
                patch.dict("os.environ", {"IMAGE_PRICE_IMAGE_OUT_PER_M": "40"}, clear=True):
            real = orchestrator.openai_provider()("p", out, model="gpt-image-1", quality="high")
        self.assertEqual(real.cost_kind, cost.MEASURED)

    def test_orchestrator_keeps_the_kind_given_by_the_provider(self):
        class Est(sample.PlaceholderImageProvider):
            def __call__(self, *a, **k):
                result = super().__call__(*a, **k)
                result.cost_usd, result.cost_kind = 0.04, cost.ESTIMATED
                return result
        tracker = cost.BudgetTracker(cost.Budget())
        manifest = orchestrator.generate_scene_images(sample.moral_plan(), tenant_id="t", work_dir=self.tmp, provider=Est(),
                                                      tracker=tracker, expected_unit_usd=0.05)
        self.assertTrue(all(m["cost_kind"] == cost.ESTIMATED for m in manifest.values()))
        self.assertEqual(set(tracker.total_by_kind()), {cost.ESTIMATED})

    def test_voice_cost_from_characters_is_estimated(self):
        out = str(self.tmp / "v.mp3")
        with patch.object(tts, "synthesize_with_timestamps", return_value=[]):
            result = voice.elevenlabs_provider({"ELEVENLABS_USD_PER_1K_CHARS": "0.18"})("hello", VOICE, out)
        self.assertEqual(result.cost_kind, cost.ESTIMATED)

    @needs_ffmpeg
    def test_voice_manifest_keeps_the_kind(self):
        class Est(voice.SimulatedVoiceProvider):
            def __call__(self, *a):
                result = super().__call__(*a)
                result.cost_usd, result.cost_kind = 0.01, cost.ESTIMATED
                return result
        tracker = cost.BudgetTracker(cost.Budget())
        plan = sample.moral_plan()
        plan["voice_id"] = VOICE
        manifest = voice.synthesize_story(plan, tenant_id="t", work_dir=self.tmp, provider=Est("en"), tracker=tracker,
                                          voice_id=None, rate_per_1k=0.18)
        self.assertTrue(all(m["cost_kind"] == cost.ESTIMATED for m in manifest.values()))


class TestShortSceneGuard(unittest.TestCase):
    def test_scene_shorter_than_the_transition_plus_margin_is_refused(self):
        slot = {"id": "s1", "transition": "crossfade", "camera": "still", "duration": 0.7, "start": 0, "end": 0.7, "audio_start": 0}
        with self.assertRaises(ValueError):
            render.render_story(["c.jpg"], {"scenes": [slot], "total_s": 1}, ["a.mp3"], "o.mp4", "w")


if __name__ == "__main__":
    unittest.main()
