"""Drapeau NARRATIVE_INTELLIGENCE_ENABLED : désactivé par défaut, ne déclenche ni exécuteur ni appel payant, n'a aucun effet sur le code de production."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from growthos.engine.narrative_review import faceloop

PACKAGE = Path(faceloop.__file__).resolve().parent
GROWTHOS = PACKAGE.parents[1]
ROOT_REPO = PACKAGE.parents[2]


class TestFlag(unittest.TestCase):
    def test_disabled_by_default_and_only_exact_true_values_enable(self):
        self.assertFalse(faceloop.is_enabled({}))
        for value in ("", "false", "False", "0", "no", "yes", "on", "enabled", "truee", "true false", "2", "TRUE2", " ", None, 1, True):
            self.assertFalse(faceloop.is_enabled({faceloop.FLAG: value}), value)
        for value in ("true", "TRUE", " true ", "1", "True"):
            self.assertTrue(faceloop.is_enabled({faceloop.FLAG: value}), value)

    def test_the_process_environment_is_what_the_default_reads(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(faceloop.FLAG, None)
            self.assertFalse(faceloop.is_enabled())
            with self.assertRaises(faceloop.NarrativeIntelligenceDisabled):
                faceloop.ui_fixture()
        with mock.patch.dict(os.environ, {faceloop.FLAG: "true"}):
            self.assertTrue(faceloop.is_enabled())

    def test_when_disabled_nothing_is_computed_and_nothing_is_written(self):
        with mock.patch.object(faceloop, "_variant", side_effect=AssertionError("computed while disabled")), mock.patch.dict(os.environ, {faceloop.FLAG: "false"}):
            with self.assertRaises(faceloop.NarrativeIntelligenceDisabled):
                faceloop.ui_fixture()
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "fixture.json"
                with self.assertRaises(faceloop.NarrativeIntelligenceDisabled):
                    faceloop.export_ui_fixture(target)
                self.assertFalse(target.exists())
                with self.assertRaises(SystemExit):
                    faceloop.main(["--export", str(target)])
                self.assertFalse(target.exists())


class TestEnabledIsStillOfflineAndInert(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {faceloop.FLAG: "true"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_fixture_is_produced_with_no_network_attempt(self):
        attempts = []

        def boom(*args, **kwargs):
            attempts.append(args)
            raise AssertionError("network attempted")
        with mock.patch.object(socket.socket, "connect", boom), mock.patch.object(socket, "getaddrinfo", boom), mock.patch.object(socket.socket, "sendto", boom):
            fixture = faceloop.ui_fixture()
        self.assertEqual(attempts, [])
        self.assertEqual((fixture["schema"], fixture["kind"]), (faceloop.FIXTURE_SCHEMA, "LOCAL_SYNTHETIC_FIXTURE"))
        self.assertEqual(len(fixture["cases"]), 5)

    def test_the_fixture_exercises_every_decision_through_the_real_pipeline(self):
        fixture = faceloop.ui_fixture()
        decisions = {case[v]["decision"] for case in fixture["cases"] for v in ("A", "B")}
        self.assertEqual(decisions, {"accept", "accept_with_notes", "revise", "review"})
        for case in fixture["cases"]:
            for variant in ("A", "B"):
                v = case[variant]
                self.assertIn(v["analysis_status"], ("complete", "partial"))                       # « partial » = couverture partielle déclarée par le critique : décision `review`
                self.assertEqual((v["error"], v["can_auto_accept"] is True), (None, v["decision"] in ("accept", "accept_with_notes")))
                self.assertTrue(set(v["indicators"].values()) <= {"ok", "warning", "blocker", "not_evaluated"})
        revised = next(case["A"] for case in fixture["cases"] if case["topic_id"] == "D2")
        self.assertEqual((revised["decision"], revised["indicators"]["ending"], revised["reasons"]), ("revise", "blocker", ["established_blocker_f1"]))
        partial = next(case["A"] for case in fixture["cases"] if case["topic_id"] == "D4")
        self.assertEqual((partial["decision"], partial["reasons"], partial["indicators"]["clarity"]), ("review", ["coverage_clarity_partial"], "not_evaluated"))

    def test_the_fixture_is_deterministic_and_clearly_labelled_synthetic(self):
        first, second = faceloop.ui_fixture(), faceloop.ui_fixture()
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertIn("synthétiques", first["notice"])
        self.assertIn("Aucun modèle n'a été appelé", first["notice"])
        text = json.dumps(first, ensure_ascii=False)
        for secret in ("api_key", "authorization", "sk-", "OPENAI", "ANTHROPIC"):
            self.assertNotIn(secret, text)

    def test_exporting_writes_the_same_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fixture.json"
            self.assertEqual(faceloop.export_ui_fixture(target), target)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), json.loads(json.dumps(faceloop.ui_fixture())))

    def test_the_flag_alone_never_loads_an_executor_a_transport_or_a_ledger(self):
        code = ("import os, sys\n" f"sys.path.insert(0, {str(ROOT_REPO)!r})\n" "os.environ['NARRATIVE_INTELLIGENCE_ENABLED'] = 'true'\n"
                "from growthos.engine.narrative_review import faceloop\nfaceloop.ui_fixture()\n"
                "loaded = sorted(m for m in sys.modules if m.startswith('growthos.engine.narrative_review.p0d'))\nprint('LOADED', loaded)\n")
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("LOADED []", done.stdout)                                           # p0d (exécuteur, transport, journal, fenêtre) n'est jamais importé

    def test_nothing_in_the_real_call_chain_reads_the_flag(self):
        for path in (PACKAGE / "p0d").glob("*.py"):
            self.assertNotIn("NARRATIVE_INTELLIGENCE_ENABLED", path.read_text(encoding="utf-8"), path.name)    # le drapeau n'ouvre aucune porte de p0d
        source = (PACKAGE / "faceloop.py").read_text(encoding="utf-8")
        for forbidden in ("from .p0d", "import p0d", "executor", "transport", "OPENAI_API_KEY", "requests", "urllib", "http.client"):
            self.assertNotIn(forbidden, source.split('"""', 2)[2], forbidden)

    def test_with_the_flag_on_a_real_call_still_needs_everything_else(self):
        from growthos.engine.narrative_review import contract as c
        from growthos.engine.narrative_review.p0d import authorization as au
        window = au.Window()
        with self.assertRaises(c.ReviewError):
            window.check()                                                                   # aucune fenêtre ouverte : aucun appel, drapeau ou non
        with self.assertRaises(TypeError):
            window.open(None, egress_attestation_sha256="e" * 64, tokenizer_validation=None)   # contrôleur réseau obligatoire


class TestNoProductionBehaviourChange(unittest.TestCase):
    def test_no_file_outside_the_package_imports_narrative_review(self):
        offenders = []
        skip = {".git", ".worktrees", ".artifacts", "venv", ".venv", "node_modules", "__pycache__", "output", "dist", "build"}
        for dirpath, dirnames, filenames in os.walk(GROWTHOS):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix == ".py" and PACKAGE not in path.parents:
                    try:
                        if "narrative_review" in path.read_text(encoding="utf-8"):
                            offenders.append(path.relative_to(GROWTHOS).as_posix())
                    except (UnicodeDecodeError, OSError):
                        pass
        self.assertEqual(offenders, [])                                                      # ni worker, ni pipeline, ni prompts, ni Quiz, ni Story Visual

    def test_the_package_import_loads_no_network_client_or_service_library(self):
        nl = chr(10)
        code = ("import sys" + nl + f"sys.path.insert(0, {str(ROOT_REPO)!r})" + nl + "import growthos.engine.narrative_review" + nl +
                "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('requests', 'httpx', 'openai', 'anthropic', 'supabase', 'aiohttp', 'urllib3'))" + nl +
                "print('CLIENTS', bad)" + nl)
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("CLIENTS []", done.stdout)


if __name__ == "__main__":
    unittest.main()
