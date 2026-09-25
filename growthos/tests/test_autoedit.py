import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import autoedit, autoedit_captions, autoedit_media, autoedit_music, autoedit_repo, autoedit_run

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

    def test_hype_turns_a_strong_audio_peak_into_bounded_effects(self):
        source = autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 30.0)
        event = {"id": "impact", "type": "audio_peak", "startSeconds": 5.0, "endSeconds": 9.0, "score": 95}
        plan = autoedit.plan_edit([event], {"focus": "best", "style": "hype", "durationSeconds": 15}, source, 30.0)
        decision = plan["decisions"][0]
        self.assertEqual(decision["effect"], "freeze")
        self.assertEqual(decision["zoom"], "punch")
        self.assertEqual(decision["transitionOut"], "flash")
        self.assertEqual(decision["freezeSeconds"], 0.25)
        self.assertLessEqual(plan["durationSeconds"], 15)


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

    def test_rejects_unknown_or_unbounded_creative_effects(self):
        self._assert_invalid(lambda p: p["decisions"][0].update(zoom="teleport"))
        self._assert_invalid(lambda p: p["decisions"][0].update(transitionOut="spin"))
        self._assert_invalid(lambda p: p["decisions"][0].update(freezeSeconds=2))


class TestCreativeRender(unittest.TestCase):
    def test_renderer_executes_speed_zoom_freeze_and_flash(self):
        plan = _valid_plan()
        plan["decisions"][0].update(speed=0.75, effect="freeze", zoom="punch", transitionOut="flash", freezeSeconds=0.25)
        with tempfile.TemporaryDirectory() as work:
            output = str(Path(work) / "result.mp4")
            commands = []
            def fake_run(command, **_kwargs):
                commands.append(command)
                Path(output).write_bytes(b"video")
                return Mock(stdout="", stderr="")
            with patch.object(autoedit_media, "probe_has_audio", return_value=False), patch.object(autoedit_media, "_run", side_effect=fake_run):
                autoedit_media.render_plan("source.mp4", plan, output)
        graph = commands[0][commands[0].index("-filter_complex") + 1]
        self.assertIn("setpts=(PTS-STARTPTS)/0.75000", graph)
        self.assertIn("scale=778:1382", graph)
        self.assertIn("tpad=stop_mode=clone:stop_duration=0.250", graph)
        self.assertIn("fade=t=out", graph)

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


class TestGeneralProfileNotes(unittest.TestCase):
    def test_general_profile_quality_flag_does_not_mention_sports(self):
        updates = []
        real = Mock(simulated=False)
        real.name = "real"
        real.analyze.return_value = autoedit.AnalysisResult(
            events=autoedit.SimulatedAnalyzer().analyze(autoedit.SourceVideo(JOB_ID, PATH, "m.mp4", 90.0)).events,
            duration_seconds=90.0, analysis_cost=0.0, simulated=False, analyzer="real",
            notes=["Analyse locale limitée aux signaux visuels et audio : vérifiez les actions sportives et le joueur ciblé."],
        )
        with (
            patch.multiple(
                autoedit_repo,
                update_job=Mock(side_effect=lambda c, jid, **f: updates.append(f)),
                source_exists=Mock(return_value=True), download_source=Mock(return_value="s.mp4"),
                reserve_credit=Mock(return_value=True), refund_credit=Mock(return_value=True),
                upload_result=Mock(side_effect=lambda c, path, local, ct: path),
            ),
            patch.object(autoedit_media, "render_plan", return_value="r.mp4"),
            patch.object(autoedit_run, "_maybe_add_captions", side_effect=lambda run, s, r, *a: r),
            patch.object(autoedit_run.poster, "extract_poster", return_value="p.jpg"),
        ):
            status = autoedit_run.process_job(object(), _job(profile="general", focus="best"), real)
        self.assertEqual(status, "review")
        flags = " ".join(updates[-1]["quality"]["flags"])
        self.assertNotIn("sportive", flags)
        self.assertNotIn("joueur", flags)


class TestRenderFilterOrder(unittest.TestCase):
    def test_slow_motion_is_applied_after_zoompan_so_video_keeps_audio_length(self):
        plan = {"style": "cinematic", "decisions": [{
            "startSeconds": 0.0, "endSeconds": 4.0, "speed": 0.75, "zoom": "progressive",
            "transitionOut": "cut", "freezeSeconds": 0.0,
        }]}
        import tempfile
        out = Path(tempfile.mkdtemp()) / "out.mp4"
        with (
            patch.object(autoedit_media, "probe_has_audio", return_value=True),
            patch.object(autoedit_media, "_run", side_effect=lambda cmd: out.write_bytes(b"x")) as run,
        ):
            autoedit_media.render_plan("src.mp4", plan, str(out))
        graph = run.call_args.args[0][run.call_args.args[0].index("-filter_complex") + 1]
        self.assertLess(graph.index("zoompan"), graph.index("setpts=(PTS-STARTPTS)/0.75000"))
        self.assertIn("atempo=0.75000", graph)


class TestCaptionScale(unittest.TestCase):
    def test_captions_use_the_1080x1920_canvas_the_styles_are_calibrated_for(self):
        words = [{"text": "hello", "start": 0.0, "end": 0.4}]
        with (
            patch.object(autoedit_captions.captions, "write_ass", return_value="x.ass") as write_ass,
            patch.object(autoedit_captions, "_run"),
            patch.object(autoedit_captions.Path, "exists", return_value=True),
            patch.object(autoedit_captions.Path, "stat", return_value=Mock(st_size=10)),
        ):
            autoedit_captions.burn("in.mp4", words, "out.mp4", ".")
        self.assertEqual(write_ass.call_args.args[3], "1080x1920")


class TestSilentSource(unittest.TestCase):
    def test_no_audio_stream_yields_no_audio_peaks_without_running_ffmpeg(self):
        with (
            patch.object(autoedit_media, "probe_has_audio", return_value=False),
            patch.object(autoedit_media, "_run") as run,
        ):
            self.assertEqual(autoedit_media.detect_audio_peaks("muet.mp4"), [])
        run.assert_not_called()


class TestMusic(unittest.TestCase):
    def _run(self):
        run = Mock()
        run.report = {}
        return run

    def test_source_with_sound_keeps_its_audio(self):
        run, quality, usage = self._run(), {"flags": [], "manualReview": False}, {"renderCost": None}
        with (
            patch.object(autoedit_media, "probe_has_audio", return_value=True),
            patch.object(autoedit_music, "mean_volume_db", return_value=-20.0),
            patch.object(autoedit_music, "compose") as compose,
        ):
            out = autoedit_run._maybe_add_music(run, "src.mp4", "r.mp4", "hype", ".", quality, usage)
        self.assertEqual(out, "r.mp4")
        compose.assert_not_called()
        self.assertEqual(run.report["music"], {"added": False, "reason": "source_has_audio"})

    def test_silent_source_gets_generated_music_with_cost(self):
        run, quality, usage = self._run(), {"flags": [], "manualReview": False}, {"renderCost": None}
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k", "AUTOEDIT_MUSIC_USD_PER_MIN": "0.15"}),
            patch.object(autoedit_media, "probe_has_audio", return_value=False),
            patch.object(autoedit_media, "probe_duration", return_value=30.0),
            patch.object(autoedit_music, "compose", return_value="music.mp3") as compose,
            patch.object(autoedit_music, "mux_music", return_value="final.mp4"),
        ):
            out = autoedit_run._maybe_add_music(run, "src.mp4", "r.mp4", "cinematic", ".", quality, usage)
        self.assertEqual(out, "final.mp4")
        self.assertEqual(compose.call_args.args[:2], ("cinematic", 30.0))
        self.assertTrue(run.report["music"]["added"])
        self.assertEqual(run.report["music"]["reason"], "no_audio")
        self.assertEqual(usage["renderCost"], 0.075)
        self.assertEqual(quality["flags"], [])

    def test_quiet_audio_track_counts_as_silent(self):
        with patch.object(autoedit_music, "mean_volume_db", return_value=-70.0):
            self.assertEqual(autoedit_music.silence_reason("x.mp4", True), "silent")
        with patch.object(autoedit_music, "mean_volume_db", return_value=-30.0):
            self.assertIsNone(autoedit_music.silence_reason("x.mp4", True))

    def test_music_failure_keeps_the_edit_and_flags_it(self):
        run, quality, usage = self._run(), {"flags": [], "manualReview": False}, {"renderCost": None}
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}),
            patch.object(autoedit_media, "probe_has_audio", return_value=False),
            patch.object(autoedit_media, "probe_duration", return_value=15.0),
            patch.object(autoedit_music, "compose", side_effect=RuntimeError("HTTP 500")),
        ):
            out = autoedit_run._maybe_add_music(run, "src.mp4", "r.mp4", "hype", ".", quality, usage)
        self.assertEqual(out, "r.mp4")
        self.assertFalse(run.report["music"]["added"])
        self.assertTrue(quality["manualReview"])
        self.assertTrue(any("Musique non ajoutée" in f for f in quality["flags"]))

    def test_detection_failure_never_fails_the_job(self):
        run = self._run()
        with patch.object(autoedit_media, "probe_has_audio", side_effect=RuntimeError("ffprobe")):
            out = autoedit_run._maybe_add_music(run, "src.mp4", "r.mp4", "hype", ".", {"flags": []}, {})
        self.assertEqual(out, "r.mp4")
        self.assertEqual(run.report["music"]["reason"], "detection_failed")

    def test_music_can_be_disabled(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k", "AUTOEDIT_MUSIC": "off"}):
            self.assertFalse(autoedit_music.music_enabled())
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}):
            os.environ.pop("AUTOEDIT_MUSIC", None)
            self.assertTrue(autoedit_music.music_enabled())

    def test_every_style_has_an_instrumental_prompt(self):
        for style in ("hype", "cinematic", "clean", "emotional"):
            self.assertIn("instrumental", autoedit_music.STYLE_PROMPTS[style].lower())


class TestGeneralCaptions(unittest.TestCase):
    def test_no_speech_keeps_the_edit(self):
        run = Mock(report={})
        quality, usage = {"flags": [], "manualReview": False}, {"analysisCost": None}
        with (
            patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"}),
            patch.object(autoedit_media, "probe_has_audio", return_value=True),
            patch.object(autoedit_captions, "transcribe", return_value=[]) as transcribe,
        ):
            out = autoedit_run._maybe_add_captions(
                run, "source.mp4", "rendered.mp4", {"decisions": []}, ".", quality, usage,
            )
        self.assertEqual(out, "rendered.mp4")
        transcribe.assert_called_once_with("rendered.mp4")
        self.assertEqual(run.report["captions"]["reason"], "no_speech")


if __name__ == "__main__":
    unittest.main()
