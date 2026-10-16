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
        env = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test"})
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
