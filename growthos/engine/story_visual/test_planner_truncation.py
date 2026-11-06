"""Une réponse du planificateur coupée par la limite de sortie est nommée comme telle, facturée à son usage réel, et jamais relancée à l'identique."""
import os
import unittest
from unittest.mock import patch

from growthos.engine.story_visual import cost, planner

ENV = {"STORY_PLANNER_MODEL": "m", "OPENAI_API_KEY": "k", "STORY_PLAN_INPUT_TOKEN_CEILING": "100",
       "STORY_PLAN_MAX_OUTPUT_TOKENS": "50", "SCRIPT_PRICE_IN_PER_M": "1", "SCRIPT_PRICE_OUT_PER_M": "2"}


class Resp:
    status_code, text = 200, ""

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def message(text):
    return [{"type": "message", "content": [{"type": "output_text", "text": text}]}]


TRUNCATED = {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": message('{"title": "Le renard", "scenes": [{"id": "s1"'),
             "usage": {"input_tokens": 7, "output_tokens": 50}}


def call(body):
    with patch.dict(os.environ, ENV, clear=True), patch.object(planner.requests, "post", side_effect=[Resp({"input_tokens": 7}), Resp(body)]):
        return planner.openai_chat_provider()("p")


class TestTruncation(unittest.TestCase):
    def test_a_truncated_response_is_named_and_keeps_the_real_usage(self):
        result = call(TRUNCATED)
        self.assertIsNone(result.text)  # the partial JSON is never parsed, nor logged
        self.assertTrue(result.error.startswith("output_truncated"))
        self.assertIn("50 output tokens", result.error)
        self.assertIn("STORY_PLAN_MAX_OUTPUT_TOKENS", result.error)
        self.assertEqual(result.usage, {"input": 7, "output": 50})  # what was really spent is recorded
        self.assertTrue(result.call_made)

    def test_truncation_with_no_message_at_all_is_still_a_truncation(self):
        result = call({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": [{"type": "reasoning"}],
                       "usage": {"input_tokens": 7, "output_tokens": 50}})
        self.assertTrue(result.error.startswith("output_truncated"))

    def test_other_responses_are_unchanged(self):
        ok = call({"status": "completed", "output": message("{}"), "usage": {"input_tokens": 7, "output_tokens": 9}})
        self.assertEqual((ok.text, ok.error, ok.usage), ("{}", None, {"input": 7, "output": 9}))
        filtered = call({"status": "incomplete", "incomplete_details": {"reason": "content_filter"}, "output": message("{}"),
                         "usage": {"input_tokens": 7, "output_tokens": 9}})
        self.assertEqual((filtered.text, filtered.error), ("{}", None))  # only the output limit is treated as a truncation

    def test_a_truncated_attempt_is_not_repeated_and_is_billed_once(self):
        calls = []

        def provider(prompt):
            calls.append(prompt)
            with patch.dict(os.environ, ENV, clear=True), patch.object(planner.requests, "post", side_effect=[Resp({"input_tokens": 7}), Resp(TRUNCATED)]):
                return planner.openai_chat_provider()(prompt)

        tracker = cost.BudgetTracker(cost.Budget(1.0, 1.0))
        request = planner.PlanRequest(idea="Un renard qui ne sait pas dire non.", story_type="moral", language="fr", target_duration_s=60)
        with patch.dict(os.environ, ENV, clear=True):
            result = planner.plan_story(request, provider, tracker, expected_call_usd=0.0001, env=ENV)
        self.assertIsNone(result.plan)
        self.assertEqual(len(calls), 1)  # the same prompt with the same limit would be cut the same way: no second paid call
        self.assertEqual(result.attempts, 1)
        self.assertTrue(result.errors[0].startswith("planner provider failed: output_truncated"))
        self.assertAlmostEqual(result.cost_usd, (7 * 1 + 50 * 2) / 1_000_000)  # 0.000107 $: the real spend of the cut call


if __name__ == "__main__":
    unittest.main()
