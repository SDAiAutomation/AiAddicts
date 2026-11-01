"""The pilot pre-flight is offline and read-only: no network, no provider, no secret value in its output, and it only says GO when everything is set."""
import io
from pathlib import Path
import socket
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import story_visual_pilot_preflight as pre

SECRET = "sk-test-SECRET-VALUE-123456"
READY = {
    "ADMIN_USER_IDS": "11111111-2222-4333-8444-555555555555", "OPENAI_API_KEY": SECRET, "ELEVENLABS_API_KEY": SECRET + "x", "SUPABASE_SERVICE_ROLE_KEY": SECRET + "y",
    "SUPABASE_URL": "https://example.supabase.co", "IMAGE_MODEL_PREMIUM": "gpt-image-2.5-flare", "IMAGE_FINAL_QUALITY": "low",
    "STORY_IMAGE_USD_EACH": "0.012", "ELEVENLABS_USD_PER_1K_CHARS": "0.30", "STORY_RENDER_USD": "0", "STORY_STORAGE_USD": "0.01",
    "SCRIPT_PRICE_IN_PER_M": "0", "SCRIPT_PRICE_OUT_PER_M": "0", "STORY_PLAN_TOKENS_IN": "0", "STORY_PLAN_TOKENS_OUT": "0",
    "STORY_BUDGET_USD": "1.0", "STORY_BUDGET_PREFERRED_USD": "0.5", "STORY_VISUAL_MAX_JOBS_PER_DAY": "1", "STORY_DEFAULT_VOICE_ID": "VoiceId12345",
}


def run(env, *extra):
    buffer = io.StringIO()
    with patch("socket.socket", side_effect=AssertionError("the pre-flight must never open a network connection")):
        code = pre.main(list(extra), env=dict(env), out=lambda line: buffer.write(line + "\n"))
    return code, buffer.getvalue()


class TestPreflight(unittest.TestCase):
    def test_a_fully_configured_test_worker_is_ready_and_nothing_secret_is_printed(self):
        code, text = run(READY)
        self.assertEqual(code, 0, text)
        self.assertIn("PRÊT", text)
        for value in (SECRET, SECRET + "x", SECRET + "y", "example.supabase.co"):
            self.assertNotIn(value, text)  # only « présente » / « absente »
        self.assertIn("OPENAI_API_KEY : présente", text)
        self.assertIn("soumis à l'autorisation explicite", text)

    def test_the_default_environment_is_not_ready(self):
        code, text = run({})
        self.assertEqual(code, 1)
        for point in ("tarif d'une image", "plafond STORY_BUDGET_USD", "OPENAI_API_KEY", "ADMIN_USER_IDS", "voix"):
            self.assertIn(point, text)
        self.assertIn("éteint (normal avant le pilote)", text)

    def test_each_blocking_point_blocks(self):
        for name in ("STORY_IMAGE_USD_EACH", "ELEVENLABS_USD_PER_1K_CHARS", "STORY_RENDER_USD", "STORY_STORAGE_USD", "STORY_BUDGET_USD", "OPENAI_API_KEY",
                     "ELEVENLABS_API_KEY", "ADMIN_USER_IDS", "STORY_DEFAULT_VOICE_ID", "SCRIPT_PRICE_IN_PER_M"):
            with self.subTest(missing=name):
                env = {k: v for k, v in READY.items() if k != name}
                self.assertEqual(run(env)[0], 1)

    def test_a_cap_above_the_pilot_ceiling_blocks_and_a_unit_cost_below_the_measured_one_warns(self):
        self.assertEqual(run({**READY, "STORY_BUDGET_USD": "2.0"})[0], 1)
        self.assertEqual(run({**READY, "STORY_BUDGET_USD": "2.0"}, "--max-usd", "2.0")[0], 0)
        code, text = run({**READY, "STORY_IMAGE_USD_EACH": "0.001"})
        self.assertEqual(code, 0)
        self.assertIn("inférieur au coût mesuré", text)

    def test_the_worst_case_with_regenerations_must_fit_the_cap(self):
        code, text = run({**READY, "STORY_BUDGET_USD": "0.25", "STORY_BUDGET_PREFERRED_USD": "0.2"})  # nominal ~0.31 $ with these rates
        self.assertEqual(code, 1)
        self.assertIn("au pire", text)

    def test_the_engine_flag_is_reported_never_changed(self):
        code, text = run({**READY, "STORY_VISUAL_ENABLED": "1"})
        self.assertEqual(code, 0)
        self.assertIn("ACTIVÉ", text)

    def test_unmeasured_model_and_quality_are_flagged(self):
        env = {k: v for k, v in READY.items() if k not in ("IMAGE_MODEL_PREMIUM", "IMAGE_FINAL_QUALITY")}
        env["OPENAI_IMAGE_QUALITY"] = "medium"
        _, text = run(env)
        self.assertIn("le coût n'a été mesuré que pour gpt-image-2.5-flare / low", text)

    def test_it_never_reads_an_env_file_or_imports_a_provider_client(self):
        source = Path(pre.__file__).read_text(encoding="utf-8")
        for forbidden in ("load_dotenv", "dotenv", ".env\"", "requests.", "urllib", "openai_images.generate", "elevenlabs_provider", "get_service_client"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
