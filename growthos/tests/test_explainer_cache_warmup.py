"""Le premier vrai plan peuple le cache avant les appels Anthropic concurrents."""
import importlib
import sys
import threading
import types
import unittest
from unittest.mock import patch

from engine.explainer import llm


class CacheWarmupTests(unittest.TestCase):
    def test_first_stream_finishes_before_later_streams_start(self):
        fake_validate = types.ModuleType("engine.explainer.validate")
        fake_validate.validate_plan = lambda *args: {"ok": True, "stage": "valid", "errors": [], "warnings": []}
        previous = sys.modules.pop("engine.explainer.animator", None)
        try:
            with patch.dict(sys.modules, {"engine.explainer.validate": fake_validate}):
                animator = importlib.import_module("engine.explainer.animator")
                events = []
                lock = threading.Lock()

                class Stream:
                    def __init__(self, name):
                        self.name = name

                    def __enter__(self):
                        with lock:
                            events.append(("start", self.name))
                        return self

                    def __exit__(self, *_):
                        return False

                    def get_final_message(self):
                        with lock:
                            events.append(("finish", self.name))
                        usage = types.SimpleNamespace(input_tokens=1, output_tokens=1,
                                                      cache_read_input_tokens=0, cache_creation_input_tokens=600)
                        return types.SimpleNamespace(usage=usage, stop_reason="end_turn",
                                                     content=[types.SimpleNamespace(type="text", text="S.grid(true);")])

                class Client:
                    class Messages:
                        def stream(self, **kwargs):
                            return Stream(kwargs["messages"][0]["content"])

                    messages = Messages()

                jobs = [{"plan_id": str(i), "brief": str(i), "duration": 2.0, "anchors": {}} for i in range(3)]
                with patch.object(llm, "client", return_value=Client()), patch.object(animator, "system_prompt", return_value="stable prefix"):
                    results = animator.animate_all(llm.Spend(limit_usd=10), jobs)
                self.assertEqual([result["id"] for result in results], ["0", "1", "2"])
                self.assertLess(events.index(("finish", "0")), events.index(("start", "1")))
                self.assertLess(events.index(("finish", "0")), events.index(("start", "2")))
        finally:
            sys.modules.pop("engine.explainer.animator", None)
            if previous is not None:
                sys.modules["engine.explainer.animator"] = previous


if __name__ == "__main__":
    unittest.main()
