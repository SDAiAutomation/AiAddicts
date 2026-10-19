import os
import unittest
from unittest import mock

from engine import moderation

SCRIPT = {"title": "Un titre", "blocks": [{"text": "du texte"}], "n": 3}


class _Resp:
    def __init__(self, cats):
        self.cats = cats

    def raise_for_status(self):
        pass

    def json(self):
        return {"results": [{"categories": self.cats}]}


def _post(cats):
    return mock.patch.object(moderation.requests, "post", lambda *a, **k: _Resp(cats))


class ModerationTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test", "FRAUD_CHECK_ENABLED": "0"})
        env.start()
        self.addCleanup(env.stop)
        for k in ("MODERATION_ENABLED", "MODERATION_FAIL_CLOSED"):
            os.environ.pop(k, None)

    def test_clean_script_passes(self):
        with _post({"violence": False}):
            moderation.check_script(SCRIPT)

    def test_grave_category_blocks(self):
        with _post({"sexual/minors": True, "violence": True}):
            with self.assertRaisesRegex(moderation.ModerationError, "sexual/minors"):
                moderation.check_script(SCRIPT)

    def test_plain_violence_is_not_blocked(self):
        with _post({"violence": True, "harassment": True}):
            moderation.check_script(SCRIPT)

    def test_service_down_fails_open_then_closed(self):
        def boom(*a, **k):
            raise moderation.requests.ConnectionError("down")

        with mock.patch.object(moderation.requests, "post", boom):
            moderation.check_script(SCRIPT)
            os.environ["MODERATION_FAIL_CLOSED"] = "1"
            with self.assertRaises(moderation.ModerationError):
                moderation.check_script(SCRIPT)

    def test_disabled_makes_no_call(self):
        os.environ["MODERATION_ENABLED"] = "0"
        with mock.patch.object(moderation.requests, "post", side_effect=AssertionError("appel inattendu")):
            moderation.check_script(SCRIPT)

    def test_all_strings_are_sent(self):
        sent = {}

        def fake(url, headers, json, timeout):
            sent["input"] = json["input"]
            return _Resp({})

        with mock.patch.object(moderation.requests, "post", fake):
            moderation.check_script(SCRIPT)
        self.assertIn("du texte", sent["input"][0])
        self.assertIn("Un titre", sent["input"][0])


class AssemblerHookTests(unittest.TestCase):
    def test_refused_script_reserves_no_credit(self):
        from engine import assembler

        data = {"title": "x"}
        with mock.patch("engine.assembler.db.get_service_client"), \
             mock.patch("engine.assembler.repo.get_script", return_value=data), \
             mock.patch("engine.assembler.script_module.normalize_script", side_effect=lambda d: d), \
             mock.patch("engine.assembler.script_module.validate_script"), \
             mock.patch("engine.assembler.moderation.check_script", side_effect=moderation.ModerationError("refusé")), \
             mock.patch("engine.assembler.repo.reserve_generation_credit") as reserve:
            with self.assertRaises(moderation.ModerationError):
                assembler.run_for_content_item("item")
        reserve.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class _Claude:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"content": [{"type": "text", "text": self.text}]}


class FraudCheckTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test", "OPENAI_API_KEY": "test"})
        env.start()
        self.addCleanup(env.stop)
        for k in ("MODERATION_ENABLED", "MODERATION_FAIL_CLOSED", "FRAUD_CHECK_ENABLED"):
            os.environ.pop(k, None)

    def _run(self, claude_text, openai_cats=None):
        def post(url, **k):
            return _Claude(claude_text) if "anthropic" in url else _Resp(openai_cats or {})

        return mock.patch.object(moderation.requests, "post", post)

    def test_scam_howto_is_blocked_with_category(self):
        with self._run('{"blocked": true, "category": "fraud", "reason": "mode d\'emploi"}'):
            with self.assertRaisesRegex(moderation.ModerationError, "fraud"):
                moderation.check_script(SCRIPT)

    def test_educational_content_passes(self):
        with self._run('```json\n{"blocked": false, "category": "none", "reason": "prévention"}\n```'):
            moderation.check_script(SCRIPT)

    def test_only_boolean_true_blocks(self):
        with self._run('{"blocked": "true", "category": "fraud", "reason": "x"}'):
            moderation.check_script(SCRIPT)

    def test_unparsable_answer_fails_open_then_closed(self):
        with self._run("je ne sais pas"):
            moderation.check_script(SCRIPT)
            os.environ["MODERATION_FAIL_CLOSED"] = "1"
            with self.assertRaises(moderation.ModerationError):
                moderation.check_script(SCRIPT)

    def test_missing_key_fails_open_then_closed(self):
        os.environ.pop("ANTHROPIC_API_KEY")
        with self._run('{"blocked": false}'):
            moderation.check_script(SCRIPT)
            os.environ["MODERATION_FAIL_CLOSED"] = "1"
            with self.assertRaises(moderation.ModerationError):
                moderation.check_script(SCRIPT)

    def test_disabled_makes_no_claude_call(self):
        os.environ["FRAUD_CHECK_ENABLED"] = "0"
        def post(url, **k):
            if "anthropic" in url:
                raise AssertionError("appel inattendu")
            return _Resp({})
        with mock.patch.object(moderation.requests, "post", post):
            moderation.check_script(SCRIPT)

    def test_openai_block_wins_before_claude_call(self):
        def post(url, **k):
            if "anthropic" in url:
                raise AssertionError("Claude ne doit pas être appelé")
            return _Resp({"hate": True})
        with mock.patch.object(moderation.requests, "post", post):
            with self.assertRaisesRegex(moderation.ModerationError, "hate"):
                moderation.check_script(SCRIPT)
