"""Script de rendu local (story_visual_local_run.py) : HORS LIGNE. Aucun fournisseur, aucune clé réelle, aucun .env.

Les fournisseurs et `pipeline.run` sont remplacés par des doubles qui ÉCHOUENT s'ils sont appelés.
"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("local_run", Path(__file__).resolve().parents[2] / "scripts" / "story_visual_local_run.py")
local_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(local_run)

FAKE_OPENAI = "sk-FAKE-openai-0123456789abcdef"
FAKE_ELEVEN = "xi-FAKE-eleven-0123456789abcdef"


def _forbidden(name):
    def boom(*a, **k):
        raise AssertionError(f"{name} appelé : aucun appel fournisseur autorisé dans ce test")
    return boom


class LocalRunBase(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        guards = {
            "openai": patch.object(local_run.orchestrator, "openai_provider", side_effect=_forbidden("openai_provider")),
            "eleven": patch.object(local_run.voice, "elevenlabs_provider", side_effect=_forbidden("elevenlabs_provider")),
            "pipeline": patch.object(local_run.pipeline, "run", side_effect=_forbidden("pipeline.run")),
        }
        self.mocks = {}
        for key, p in guards.items():
            self.mocks[key] = p.start()
            self.addCleanup(p.stop)

    def call(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = local_run.main(["--out", self.tmp.name, *argv])
        return code, out.getvalue()

    def assert_no_provider_call(self):
        for mock in self.mocks.values():
            mock.assert_not_called()


class ArgumentRefusals(LocalRunBase):
    def test_voice_rate_missing(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            local_run.main(["--out", self.tmp.name])
        self.assertNotEqual(cm.exception.code, 0)
        self.assert_no_provider_call()

    def test_cap_out_of_range(self):
        for cap in ("0", "-0.5", "1.01", "5"):
            with self.subTest(cap=cap), self.assertRaises(SystemExit) as cm:
                self.call("--voice-rate", "0.18", "--cap", cap)
            self.assertIn("STOP", str(cm.exception.code))
        self.assert_no_provider_call()

    def test_cap_boundary_one_is_accepted(self):
        code, _ = self.call("--voice-rate", "0.18", "--cap", "1")
        self.assertIn(code, (0, 2))

    def test_voice_rate_not_positive(self):
        for rate in ("0", "-0.18"):
            with self.subTest(rate=rate), self.assertRaises(SystemExit) as cm:
                self.call("--voice-rate", rate)
            self.assertIn("STOP", str(cm.exception.code))
        self.assert_no_provider_call()

    def test_image_usd_below_measured_cost(self):
        with self.assertRaises(SystemExit) as cm:
            self.call("--voice-rate", "0.18", "--image-usd", str(local_run.MEASURED_IMAGE_USD - 0.0001))
        self.assertIn("STOP", str(cm.exception.code))
        self.assert_no_provider_call()

    def test_unknown_fixture(self):
        with self.assertRaises(SystemExit) as cm:
            self.call("--voice-rate", "0.18", "--fixture", "does_not_exist_xyz")
        self.assertIn("fixture introuvable", str(cm.exception.code))
        self.assert_no_provider_call()

    def test_fixture_path_traversal_is_not_a_fixture(self):
        with self.assertRaises(SystemExit):
            self.call("--voice-rate", "0.18", "--fixture", "../../../../etc/passwd")
        self.assert_no_provider_call()


class DryRunAndGuards(LocalRunBase):
    def test_dry_run_returns_0_and_calls_no_provider(self):
        code, out = self.call("--voice-rate", "0.18")
        self.assertEqual(code, 0)
        self.assertIn("DRY-RUN terminé", out)
        self.assert_no_provider_call()
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [], "le dry-run ne doit rien écrire")

    def test_dry_run_with_keys_still_calls_nothing(self):
        os.environ.update(OPENAI_API_KEY=FAKE_OPENAI, ELEVENLABS_API_KEY=FAKE_ELEVEN)
        code, _ = self.call("--voice-rate", "0.18")
        self.assertEqual(code, 0)
        self.assert_no_provider_call()

    def test_go_without_keys_returns_2(self):
        os.environ.update(OPENAI_API_KEY="", ELEVENLABS_API_KEY="")
        code, out = self.call("--voice-rate", "0.18", "--go")
        self.assertEqual(code, 2)
        self.assertIn("Aucun appel", out)
        self.assert_no_provider_call()

    def test_go_with_only_one_key_returns_2(self):
        for env in ({"OPENAI_API_KEY": FAKE_OPENAI}, {"ELEVENLABS_API_KEY": FAKE_ELEVEN}):
            with self.subTest(env=list(env)), patch.dict(os.environ, env):
                code, _ = self.call("--voice-rate", "0.18", "--go")
                self.assertEqual(code, 2)
        self.assert_no_provider_call()

    def test_estimate_above_cap_returns_2_even_with_go_and_keys(self):
        os.environ.update(OPENAI_API_KEY=FAKE_OPENAI, ELEVENLABS_API_KEY=FAKE_ELEVEN)
        for go in ([], ["--go"]):
            with self.subTest(go=go):
                code, out = self.call("--voice-rate", "0.18", "--cap", "0.001", *go)
                self.assertEqual(code, 2)
                self.assertIn("STOP", out)
        self.assert_no_provider_call()

    def test_huge_voice_rate_exceeds_cap(self):
        code, _ = self.call("--voice-rate", "1000")
        self.assertEqual(code, 2)
        self.assert_no_provider_call()

    def test_missing_env_file_stops_before_any_call(self):
        with self.assertRaises(SystemExit) as cm:
            self.call("--voice-rate", "0.18", "--env-file", str(Path(self.tmp.name) / "absent.env"))
        self.assertIn("introuvable", str(cm.exception.code))
        self.assert_no_provider_call()


class SecretsNeverPrinted(LocalRunBase):
    def _assert_clean(self, out):
        for secret in (FAKE_OPENAI, FAKE_ELEVEN):
            self.assertNotIn(secret, out)

    def test_keys_not_printed_in_dry_run(self):
        os.environ.update(OPENAI_API_KEY=FAKE_OPENAI, ELEVENLABS_API_KEY=FAKE_ELEVEN)
        code, out = self.call("--voice-rate", "0.18")
        self.assertEqual(code, 0)
        self._assert_clean(out)
        self.assertIn("présente", out)

    def test_keys_not_printed_when_over_cap(self):
        os.environ.update(OPENAI_API_KEY=FAKE_OPENAI, ELEVENLABS_API_KEY=FAKE_ELEVEN)
        _, out = self.call("--voice-rate", "0.18", "--cap", "0.001", "--go")
        self._assert_clean(out)

    def test_keys_not_printed_when_go_blocked(self):
        os.environ.update(OPENAI_API_KEY=FAKE_OPENAI)
        with patch.object(local_run.shutil, "which", return_value=None):
            code, out = self.call("--voice-rate", "0.18", "--go")
        self.assertEqual(code, 2)
        self._assert_clean(out)

    def test_keys_absent_are_reported_as_absent(self):
        _, out = self.call("--voice-rate", "0.18")
        self.assertIn("OPENAI_API_KEY : ABSENTE", out)
        self.assertIn("ELEVENLABS_API_KEY : ABSENTE", out)


if __name__ == "__main__":
    unittest.main()
