import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import autoedit, autoedit_media, autoedit_repo, autoedit_run

JOB_ID = "11111111-1111-1111-1111-111111111111"
ORG_ID = "22222222-2222-2222-2222-222222222222"
PATH = f"{ORG_ID}/{JOB_ID}/source"


def _job(**overrides):
    job = {
        "id": JOB_ID, "organization_id": ORG_ID, "status": "analyzing", "attempts": 1,
        "input_filename": "match.mp4", "input_duration_seconds": "90.0",
        "focus": "best", "player_number": None, "style": "hype", "duration_seconds": 30,
    }
    job.update(overrides)
    return job


def _valid_plan():
    return {
        "version": autoedit.PLAN_VERSION, "durationSeconds": 10.0, "style": "hype",
        "decisions": [{
            "source": PATH, "startSeconds": 5.0, "endSeconds": 15.0, "speed": 1.0,
            "eventId": "e1", "cropTarget": None, "effect": None, "caption": None,
        }],
    }


def _validate(plan, **kw):
    kw.setdefault("source_duration", 60.0)
    kw.setdefault("allowed_sources", {PATH})
    autoedit.validate_plan(plan, **kw)


class TestSimulatedAnalyzer(unittest.TestCase):
    def _source(self, duration=90.0):
        return autoedit.SourceVideo(JOB_ID, PATH, "match.mp4", duration)

    def test_deterministic_and_within_source(self):
        a = autoedit.SimulatedAnalyzer().analyze(self._source())
        b = autoedit.SimulatedAnalyzer().analyze(self._source())
        self.assertEqual(a.events, b.events)
        self.assertTrue(a.simulated)
        self.assertEqual(a.analysis_cost, 0.0)
        for e in a.events:
            self.assertIn(e["type"], autoedit.EVENT_TYPES)
            self.assertTrue(0 <= e["startSeconds"] < e["endSeconds"] <= 90.0)

    def test_never_invents_scores(self):
        result = autoedit.SimulatedAnalyzer().analyze(self._source())
        self.assertTrue(all(e["score"] is None and e["confidence"] is None for e in result.events))

    def test_unknown_duration_is_assumed_and_disclosed(self):
        result = autoedit.SimulatedAnalyzer().analyze(self._source(duration=None))
        self.assertEqual(result.duration_seconds, 120.0)
        self.assertTrue(any("inconnue" in n for n in result.notes))

    def test_get_analyzer_rejects_unknown_name(self):
        with self.assertRaises(RuntimeError):
            autoedit.get_analyzer("vision-magic")
        self.assertEqual(autoedit.get_analyzer("simulated").name, "simulated")

    def test_signal_analyzer_is_available(self):
        self.assertEqual(autoedit.get_analyzer("signals").name, "signals")

    def test_signal_analyzer_uses_measured_scene_changes(self):
        source = autoedit.SourceVideo(JOB_ID, PATH, "match.mp4", None, "match.mp4")
        with (
            patch.object(autoedit_media, "probe_duration", return_value=20.0),
            patch.object(autoedit_media, "detect_scene_changes", return_value=[4.0, 12.0]),
            patch.object(autoedit_media, "detect_audio_peaks", return_value=[]),
        ):
            result = autoedit_media.SignalAnalyzer().analyze(source)
        self.assertFalse(result.simulated)
        self.assertEqual([event["type"] for event in result.events], ["scene_change", "scene_change"])
        self.assertEqual(result.duration_seconds, 20.0)
        self.assertTrue(result.notes)

    def test_audio_metadata_parser_keeps_timestamp_and_rms(self):
        stderr = "\n".join([
            "[Parsed_ametadata] frame:0 pts:0 pts_time:0.5",
            "[Parsed_ametadata] lavfi.astats.Overall.RMS_level=-22.4",
            "[Parsed_ametadata] frame:1 pts:1 pts_time:1.0",
            "[Parsed_ametadata] lavfi.astats.Overall.RMS_level=-inf",
        ])
        self.assertEqual(autoedit_media.parse_audio_levels(stderr), [(0.5, -22.4), (1.0, -999.0)])


class TestPlanEdit(unittest.TestCase):
    def _events(self):
        return autoedit.SimulatedAnalyzer().analyze(
            autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 90.0)
        ).events

    def test_plan_is_valid_and_fits_target(self):
        source = autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 90.0)
        events = self._events()
        plan = autoedit.plan_edit(events, {"focus": "best", "style": "hype", "durationSeconds": 15}, source, 90.0)
        self.assertLessEqual(plan["durationSeconds"], 15.0 + 1e-6)
        self.assertGreater(len(plan["decisions"]), 0)
        _validate(plan, source_duration=90.0, known_event_ids={e["id"] for e in events})
        starts = [d["startSeconds"] for d in plan["decisions"]]
        self.assertEqual(starts, sorted(starts))

    def test_goals_focus_prefers_goal_events(self):
        source = autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 90.0)
        events = [
            {"id": "a", "type": "highlight", "startSeconds": 5, "endSeconds": 20, "score": 90, "confidence": None, "subject": None, "notes": None},
            {"id": "b", "type": "goal", "startSeconds": 40, "endSeconds": 55, "score": 10, "confidence": None, "subject": None, "notes": None},
        ]
        plan = autoedit.plan_edit(events, {"focus": "goals", "style": "hype", "durationSeconds": 15}, source, 90.0)
        self.assertEqual(plan["decisions"][0]["eventId"], "b")

    def test_deterministic(self):
        source = autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 90.0)
        events = self._events()
        cfg = {"focus": "best", "style": "clean", "durationSeconds": 30}
        self.assertEqual(
            autoedit.plan_edit(events, cfg, source, 90.0), autoedit.plan_edit(events, cfg, source, 90.0)
        )

    def test_overlapping_signals_do_not_repeat_the_same_footage(self):
        source = autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 30.0)
        events = [
            {"id": "audio", "type": "audio_peak", "startSeconds": 5.0, "endSeconds": 9.0, "score": 90},
            {"id": "scene", "type": "scene_change", "startSeconds": 6.0, "endSeconds": 10.0, "score": None},
            {"id": "later", "type": "scene_change", "startSeconds": 15.0, "endSeconds": 19.0, "score": None},
        ]
        plan = autoedit.plan_edit(events, {"focus": "best", "style": "clean", "durationSeconds": 15}, source, 30.0)
        self.assertEqual([decision["eventId"] for decision in plan["decisions"]], ["audio", "later"])


class TestValidatePlan(unittest.TestCase):
    def test_valid_plan_passes(self):
        _validate(_valid_plan())

    def _assert_invalid(self, mutate, **kw):
        plan = copy.deepcopy(_valid_plan())
        mutate(plan)
        with self.assertRaises(autoedit.AutoEditError) as ctx:
            _validate(plan, **kw)
        self.assertEqual(ctx.exception.code, autoedit.ERR_PLAN_INVALID)
        self.assertFalse(ctx.exception.retryable)

    def test_rejects_out_of_bounds_timecodes(self):
        self._assert_invalid(lambda p: p["decisions"][0].update(endSeconds=75.0))

    def test_rejects_non_positive_duration(self):
        self._assert_invalid(lambda p: p["decisions"][0].update(startSeconds=10.0, endSeconds=10.0))

    def test_rejects_negative_start(self):
        self._assert_invalid(lambda p: p["decisions"][0].update(startSeconds=-1.0))

    def test_rejects_bad_speed(self):
        for speed in (0, -1, 100, float("nan"), True, None):
            self._assert_invalid(lambda p, s=speed: p["decisions"][0].update(speed=s))

    def test_rejects_unauthorized_source(self):
        self._assert_invalid(lambda p: p["decisions"][0].update(source="other-org/x/source"))

    def test_rejects_empty_and_oversized_plans(self):
        self._assert_invalid(lambda p: p.update(decisions=[]))
        self._assert_invalid(
            lambda p: p.update(decisions=[copy.deepcopy(p["decisions"][0]) for _ in range(autoedit.MAX_DECISIONS + 1)])
        )

    def test_rejects_unknown_effect_and_event(self):
        self._assert_invalid(lambda p: p["decisions"][0].update(effect="explode"))
        self._assert_invalid(lambda p: None, known_event_ids={"other"})

    def test_unknown_source_duration_skips_bounds_only(self):
        plan = _valid_plan()
        plan["decisions"][0]["endSeconds"] = 500.0
        _validate(plan, source_duration=None)

    def test_retryable_is_explicit(self):
        plan = _valid_plan()
        plan["decisions"] = []
        with self.assertRaises(autoedit.AutoEditError) as ctx:
            _validate(plan, retryable_on_failure=True)
        self.assertTrue(ctx.exception.retryable)


class TestContractViews(unittest.TestCase):
    def _row(self, **kw):
        row = {
            "id": JOB_ID, "status": "review", "progress": 100, "stage_label": "Prêt",
            "input_filename": "m.mp4", "input_duration_seconds": "90.5", "focus": "player",
            "player_number": "10", "style": "clean", "duration_seconds": 30, "error": None,
            "created_at": "t0", "updated_at": "t1", "plan": _valid_plan(),
            "quality": {"score": None, "flags": ["x"], "manualReview": True},
            "usage": {"analysisCost": 0.0, "renderCost": None, "currency": "USD"},
            "video_url": None, "poster_url": None,
        }
        row.update(kw)
        return row

    def test_job_view_matches_contract_shape(self):
        view = autoedit.to_job_view(self._row())
        self.assertEqual(view["jobId"], JOB_ID)
        self.assertEqual(view["input"], {"filename": "m.mp4", "durationSeconds": 90.5})
        self.assertEqual(view["configuration"]["playerNumber"], "10")
        self.assertEqual(set(view), {"jobId", "status", "progress", "stageLabel", "input", "configuration", "error", "createdAt", "updatedAt"})

    def test_result_only_for_review_or_completed(self):
        self.assertIsNone(autoedit.to_result_view(self._row(status="analyzing")))
        result = autoedit.to_result_view(self._row())
        self.assertEqual(result["eventsUsed"], ["e1"])
        self.assertIsNone(result["videoUrl"])
        self.assertTrue(result["quality"]["manualReview"])

    def test_result_view_never_exposes_a_stored_url(self):
        result = autoedit.to_result_view(self._row(video_url="https://public/x.mp4", expires_at="t9", purged_at=None))
        self.assertIsNone(result["videoUrl"])
        self.assertEqual(result["expiresAt"], "t9")
        self.assertFalse(result["purged"])
        self.assertTrue(autoedit.to_result_view(self._row(purged_at="t10"))["purged"])


class TestCreditCostAndFlag(unittest.TestCase):
    def test_simulated_costs_nothing(self):
        self.assertEqual(autoedit.credit_cost(autoedit.SimulatedAnalyzer()), 0)

    def test_real_analyzer_default_and_override(self):
        real = Mock(simulated=False)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOEDIT_CREDIT_COST", None)
            self.assertEqual(autoedit.credit_cost(real), 1)
        with patch.dict(os.environ, {"AUTOEDIT_CREDIT_COST": "3"}):
            self.assertEqual(autoedit.credit_cost(real), 3)

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOEDIT_ENABLED", None)
            self.assertFalse(autoedit.autoedit_enabled())
        with patch.dict(os.environ, {"AUTOEDIT_ENABLED": "true"}):
            self.assertTrue(autoedit.autoedit_enabled())

    def test_source_path_matches_storage_policy(self):
        self.assertEqual(autoedit.source_path(ORG_ID, JOB_ID), f"{ORG_ID}/{JOB_ID}/source")


class TestProcessJob(unittest.TestCase):
    def setUp(self):
        self.updates = []
        self.repo = patch.multiple(
            autoedit_repo,
            update_job=Mock(side_effect=lambda c, jid, **f: self.updates.append(f)),
            fail_job=Mock(side_effect=lambda c, jid, err, rep=None: self.updates.append({"FAILED": err, "report": rep})),
            source_exists=Mock(return_value=True),
            download_source=Mock(return_value="source.mp4"),
            reserve_credit=Mock(return_value=True),
            refund_credit=Mock(return_value=True),
        )
        self.repo.start()
        self.addCleanup(self.repo.stop)

    def _final(self):
        return self.updates[-1]

    def test_simulated_run_ends_in_review_without_video_or_credits(self):
        status = autoedit_run.process_job(object(), _job(), autoedit.SimulatedAnalyzer())
        self.assertEqual(status, "review")
        final = self._final()
        self.assertEqual(final["status"], "review")
        self.assertEqual(final["stage_label"], autoedit.STAGE_LABELS["review"])
        self.assertNotIn("video_url", final)
        self.assertTrue(final["quality"]["manualReview"])
        self.assertIn(autoedit.SIMULATED_FLAG, final["quality"]["flags"])
        self.assertEqual(final["usage"], {"analysisCost": 0.0, "renderCost": None, "currency": "USD"})
        self.assertEqual(final["run_report"]["analyzer"], "simulated")
        self.assertTrue(final["run_report"]["simulated"])
        self.assertEqual([s["status"] for s in final["run_report"]["stages"]], ["analyzing", "planning"])
        autoedit_repo.reserve_credit.assert_not_called()
        # les événements sont persistés avant le plan
        self.assertTrue(any("events" in u for u in self.updates))
        self.assertLess(
            next(i for i, u in enumerate(self.updates) if "events" in u),
            next(i for i, u in enumerate(self.updates) if u.get("status") == "review"),
        )

    def test_missing_source_fails_without_touching_credits(self):
        autoedit_repo.source_exists.return_value = False
        status = autoedit_run.process_job(object(), _job(), autoedit.SimulatedAnalyzer())
        self.assertEqual(status, "failed")
        self.assertEqual(self._final()["FAILED"]["code"], autoedit.ERR_SOURCE_MISSING)
        self.assertFalse(self._final()["FAILED"]["retryable"])
        autoedit_repo.reserve_credit.assert_not_called()
        autoedit_repo.refund_credit.assert_not_called()

    def test_insufficient_credits_fails_and_does_not_refund(self):
        real = Mock(simulated=False)
        real.name = "real"
        autoedit_repo.reserve_credit.return_value = False
        status = autoedit_run.process_job(object(), _job(), real)
        self.assertEqual(status, "failed")
        self.assertEqual(self._final()["FAILED"]["code"], autoedit.ERR_INSUFFICIENT_CREDITS)
        autoedit_repo.refund_credit.assert_not_called()
        real.analyze.assert_not_called()

    def test_failure_after_reservation_refunds(self):
        real = Mock(simulated=False)
        real.name = "real"
        real.analyze.side_effect = RuntimeError("boom")
        status = autoedit_run.process_job(object(), _job(), real)
        self.assertEqual(status, "failed")
        autoedit_repo.reserve_credit.assert_called_once()
        autoedit_repo.refund_credit.assert_called_once()
        err = self._final()["FAILED"]
        self.assertEqual(err["code"], autoedit.ERR_INTERNAL)
        self.assertTrue(err["retryable"])

    def test_real_analyzer_renders_and_ends_in_review(self):
        real = Mock(simulated=False)
        real.name = "real"
        real.analyze.return_value = autoedit.SimulatedAnalyzer().analyze(
            autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 90.0)
        )
        real.analyze.return_value = autoedit.AnalysisResult(
            events=real.analyze.return_value.events, duration_seconds=90.0,
            analysis_cost=0.01, simulated=False, analyzer="real",
        )
        uploads = []
        with (
            patch.object(autoedit_media, "render_plan", return_value="result.mp4"),
            patch.object(autoedit_repo, "upload_result", side_effect=lambda c, path, local, ct: uploads.append((path, ct)) or path),
            patch.object(autoedit_run.poster, "extract_poster", return_value="poster.jpg"),
        ):
            status = autoedit_run.process_job(object(), _job(), real)
        self.assertEqual(status, "review")
        final = self._final()
        # Rendu privé : un chemin dans autoedit-results, jamais une URL publique.
        self.assertEqual(final["result_video_path"], f"{ORG_ID}/{JOB_ID}/result.mp4")
        self.assertEqual(final["result_poster_path"], f"{ORG_ID}/{JOB_ID}/poster.jpg")
        self.assertNotIn("video_url", final)
        self.assertNotIn("poster_url", final)
        self.assertEqual(uploads, [(f"{ORG_ID}/{JOB_ID}/result.mp4", "video/mp4"), (f"{ORG_ID}/{JOB_ID}/poster.jpg", "image/jpeg")])
        self.assertIn("expires_at", final)
        self.assertIn("rendering", [u.get("status") for u in self.updates])
        autoedit_repo.refund_credit.assert_not_called()

    def test_invalid_plan_fails_non_retryable(self):
        with patch.object(autoedit, "plan_edit", return_value={**_valid_plan(), "decisions": []}):
            status = autoedit_run.process_job(object(), _job(), autoedit.SimulatedAnalyzer())
        self.assertEqual(status, "failed")
        self.assertEqual(self._final()["FAILED"]["code"], autoedit.ERR_PLAN_INVALID)


def _chain(data):
    """Faux builder PostgREST : toutes les méthodes chaînables renvoient lui-même."""
    q = Mock()
    for name in ("update", "select", "eq", "lt", "gte", "in_", "order", "limit"):
        getattr(q, name).return_value = q
    q.execute.return_value = Mock(data=data)
    return q


class TestRepo(unittest.TestCase):
    def test_claim_returns_none_when_queue_empty(self):
        client = Mock()
        client.table.side_effect = lambda name: _chain([])
        self.assertIsNone(autoedit_repo.claim_job(client))

    def test_claim_is_conditional_on_queued_status_and_bumps_attempts(self):
        queue = _chain([{"id": JOB_ID, "attempts": 1}])
        claim = _chain([{"id": JOB_ID, "attempts": 2, "status": "analyzing"}])
        others = _chain([])
        # 1: reap, 2/3: reclaim (fail, requeue), 4: select queued, 5: claim update
        tables = iter([others, others, others, queue, claim])
        client = Mock()
        client.table.side_effect = lambda name: next(tables)
        job = autoedit_repo.claim_job(client)
        self.assertEqual(job["attempts"], 2)
        payload = claim.update.call_args.args[0]
        self.assertEqual(payload["status"], "analyzing")
        self.assertEqual(payload["attempts"], 2)
        claim.eq.assert_any_call("status", "queued")

    def test_lost_race_returns_none(self):
        queue = _chain([{"id": JOB_ID, "attempts": 0}])
        tables = iter([_chain([]), _chain([]), _chain([]), queue, _chain([])])
        client = Mock()
        client.table.side_effect = lambda name: next(tables)
        self.assertIsNone(autoedit_repo.claim_job(client))

    def test_source_exists_checks_object_named_source(self):
        client = Mock()
        client.storage.from_.return_value.list.return_value = [{"name": "source"}]
        self.assertTrue(autoedit_repo.source_exists(client, ORG_ID, JOB_ID))
        client.storage.from_.assert_called_with("autoedit-sources")
        client.storage.from_.return_value.list.assert_called_with(f"{ORG_ID}/{JOB_ID}")
        client.storage.from_.return_value.list.return_value = [{"name": "other.mp4"}]
        self.assertFalse(autoedit_repo.source_exists(client, ORG_ID, JOB_ID))

    def test_download_source_writes_private_storage_payload(self):
        import tempfile
        client = Mock()
        client.storage.from_.return_value.download.return_value = b"video-bytes"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source"
            self.assertEqual(autoedit_repo.download_source(client, ORG_ID, JOB_ID, str(destination)), str(destination))
            self.assertEqual(destination.read_bytes(), b"video-bytes")
        client.storage.from_.return_value.download.assert_called_with(PATH)

    def test_credit_rpcs(self):
        client = Mock()
        client.rpc.return_value.execute.return_value = Mock(data=True)
        self.assertTrue(autoedit_repo.reserve_credit(client, JOB_ID, 2))
        client.rpc.assert_called_with("reserve_autoedit_credit", {"p_job_id": JOB_ID, "p_credits": 2})
        self.assertTrue(autoedit_repo.refund_credit(client, JOB_ID))
        client.rpc.assert_called_with("refund_autoedit_credit", {"p_job_id": JOB_ID})


class TestWorkerWiring(unittest.TestCase):
    def test_worker_module_compiles(self):
        # Une erreur de syntaxe dans worker.py casse TOUTE la génération, pas
        # seulement AutoEdit : les autres tests n'importent jamais worker.py.
        import py_compile

        py_compile.compile(str(Path(__file__).parent.parent / "worker.py"), doraise=True)


class TestRetention(unittest.TestCase):
    def test_retention_days_default_override_and_floor(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOEDIT_RETENTION_DAYS", None)
            self.assertEqual(autoedit.retention_days(), 7)
        with patch.dict(os.environ, {"AUTOEDIT_RETENTION_DAYS": "30"}):
            self.assertEqual(autoedit.retention_days(), 30)
        with patch.dict(os.environ, {"AUTOEDIT_RETENTION_DAYS": "0"}):
            self.assertEqual(autoedit.retention_days(), 1)
        with patch.dict(os.environ, {"AUTOEDIT_RETENTION_DAYS": "abc"}):
            self.assertEqual(autoedit.retention_days(), 7)

    def test_failed_job_gets_an_expiry(self):
        self.assertIn("expires_at", autoedit_repo._failed_fields({"code": "x"}))

    def test_purge_removes_source_and_results_then_marks_job(self):
        client = Mock()
        query = client.table.return_value.select.return_value.is_.return_value.lt.return_value.limit.return_value
        query.execute.return_value.data = [{"id": JOB_ID, "organization_id": ORG_ID}]
        buckets = {}
        client.storage.from_.side_effect = lambda name: buckets.setdefault(name, Mock())
        with patch.object(autoedit_repo, "update_job") as update:
            self.assertEqual(autoedit_repo.purge_expired(client), 1)
        buckets["autoedit-sources"].remove.assert_called_once_with([f"{ORG_ID}/{JOB_ID}/source"])
        buckets["autoedit-results"].remove.assert_called_once_with(
            [f"{ORG_ID}/{JOB_ID}/result.mp4", f"{ORG_ID}/{JOB_ID}/poster.jpg"]
        )
        fields = update.call_args.kwargs
        self.assertIn("purged_at", fields)
        self.assertIsNone(fields["result_video_path"])


if __name__ == "__main__":
    unittest.main()
