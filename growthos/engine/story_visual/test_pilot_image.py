"""Script du pilote artistique : aucune requête réelle (requests.post est remplacé), aucune clé réelle."""
import base64
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SPEC = importlib.util.spec_from_file_location("pilot", Path(__file__).resolve().parents[2] / "scripts" / "story_visual_pilot_image.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)

ENV = {"OPENAI_API_KEY": "sk-test-not-real", "OPENAI_IMAGE_MODEL": "model-x", "IMAGE_PRICE_IMAGE_OUT_PER_M": "40",
       "IMAGE_PRICE_TEXT_IN_PER_M": "5", "STORY_IMAGE_MAX_OUTPUT_TOKENS": "1500"}


class FakeResp:
    status_code, text, headers = 200, "", {}
    def json(self):
        buf = io.BytesIO()
        Image.new("RGB", (1024, 1536), "navy").save(buf, "JPEG")
        return {"data": [{"b64_json": base64.b64encode(buf.getvalue()).decode()}],
                "usage": {"input_tokens": 700, "output_tokens": 1400, "input_tokens_details": {"text_tokens": 700, "image_tokens": 0}}}


class Args:
    def __init__(self, tmp, go=False, cap=0.5, quality="low", env_file=None):
        self.go, self.cap, self.quality, self.env_file, self.out_dir = go, cap, quality, env_file, str(tmp)


class TestPilot(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_pilot(self, env, args, post=None):
        calls = []
        def fake_post(*a, **k):
            calls.append((a, k))
            return (post or FakeResp)()
        with patch.dict(os.environ, env, clear=True):
            code = pilot.run(args, post=fake_post)
        return code, calls

    def test_prompt_forbids_text_and_carries_the_metaphor(self):
        prompt = pilot.build_prompt()
        self.assertIn("SANS AUCUN TEXTE", prompt)
        self.assertIn("porte", prompt)
        self.assertIn("foulard bleu nuit", prompt)

    def test_dry_run_calls_nothing(self):
        code, calls = self.run_pilot(ENV, Args(self.tmp))
        self.assertEqual((code, calls), (0, []))

    def test_each_missing_condition_stops_before_any_call(self):
        for drop in ENV:
            env = {k: v for k, v in ENV.items() if k != drop}
            code, calls = self.run_pilot(env, Args(self.tmp, go=True))
            self.assertEqual((code, calls), (2, []), drop)

    def test_bound_above_cap_stops(self):
        env = dict(ENV, STORY_IMAGE_MAX_OUTPUT_TOKENS="20000")  # 0,8 $ + entrée
        code, calls = self.run_pilot(env, Args(self.tmp, go=True))
        self.assertEqual((code, calls), (2, []))
        self.assertEqual(self.run_pilot(ENV, Args(self.tmp, go=True, cap=0.01))[0], 2)

    def test_cap_cannot_be_raised_above_half_a_dollar(self):
        with self.assertRaises(SystemExit):
            pilot.main(["--cap", "5"])
        with self.assertRaises(SystemExit):
            pilot.main(["--cap", "nan"])

    def test_go_makes_exactly_one_request_and_records_a_measured_cost(self):
        code, calls = self.run_pilot(ENV, Args(self.tmp, go=True))
        self.assertEqual((code, len(calls)), (0, 1))
        (args, kwargs) = calls[0]
        self.assertEqual(kwargs["json"]["model"], "model-x")
        self.assertEqual((kwargs["json"]["n"], kwargs["json"]["size"], kwargs["json"]["quality"]), (1, "1024x1536", "low"))
        report = json.loads(next(self.tmp.glob("pilot-*.json")).read_text(encoding="utf-8"))
        self.assertEqual((report["calls"], report["retries"], report["cost"]["kind"]), (1, 0, "MEASURED"))
        self.assertAlmostEqual(report["cost"]["usd"], (1400 * 40 + 700 * 5) / 1e6)
        self.assertEqual(report["cost_bound"]["basis"], "ESTIMATION (borne), jamais une mesure")
        self.assertNotIn("sk-test", json.dumps(report))  # la clé n'est jamais écrite
        self.assertEqual(len(list(self.tmp.glob("pilot-*.jpg"))), 1)

    def test_http_error_and_network_error_are_never_retried(self):
        class Bad(FakeResp):
            status_code, text = 429, "rate limited"
        code, calls = self.run_pilot(ENV, Args(self.tmp, go=True), Bad)
        self.assertEqual((code, len(calls)), (1, 1))
        self.assertEqual(json.loads(next(self.tmp.glob("pilot-*.json")).read_text())["cost"]["kind"], "UNKNOWN")
        import requests
        def boom(*a, **k):
            raise requests.ConnectionError("down")
        with patch.dict(os.environ, ENV, clear=True):
            self.assertEqual(pilot.run(Args(self.tmp, go=True), post=boom), 1)

    def test_missing_usage_is_reported_as_unknown_not_zero(self):
        class NoUsage(FakeResp):
            def json(self):
                data = super().json()
                data.pop("usage")
                return data
        self.run_pilot(ENV, Args(self.tmp, go=True), NoUsage)
        self.assertEqual(json.loads(next(self.tmp.glob("pilot-*.json")).read_text())["cost"]["kind"], "UNKNOWN")

    def test_env_file_is_loaded_without_printing_values(self):
        env_file = self.tmp / "x.env"
        env_file.write_text("OPENAI_API_KEY=sk-from-file\nOPENAI_IMAGE_MODEL=m\n")
        import contextlib
        out = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(out):
            pilot.run(Args(self.tmp, env_file=str(env_file)))
        self.assertIn("présente", out.getvalue())
        self.assertNotIn("sk-from-file", out.getvalue())
        with self.assertRaises(SystemExit):
            pilot.run(Args(self.tmp, env_file=str(self.tmp / "missing.env")))


if __name__ == "__main__":
    unittest.main()
