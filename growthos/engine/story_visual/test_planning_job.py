"""Planification asynchrone hors ligne : aucun fournisseur réel ni dépense."""
import copy
import json
import unittest

from growthos.engine.story_visual import cost, formats, planner, planning_job, sample

ENV = {"STORY_PLANNER_MODEL": "test-model", "STORY_PLAN_INPUT_TOKEN_CEILING": "5000",
       "STORY_PLAN_MAX_OUTPUT_TOKENS": "3500", "SCRIPT_PRICE_IN_PER_M": "1",
       "SCRIPT_PRICE_OUT_PER_M": "4"}


class FakeLLM:
    def __init__(self, result):
        self.result, self.prompts = result, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.result


def script_for(idea="Un petit renard nourrit chaque jour un loup qui était autrefois son ennemi."):
    return {"content_format": "story_visual", "story_plan": None, "simulation": False,
            "story_planning": {"idempotency_key": "plan:1234567890123456", "confirmed_max_usd": 0.04,
                               "prompt_version": formats.PLANNER_PROMPT_VERSION,
                               "request": {"idea": idea, "story_type": "moral", "language": "fr",
                                           "target_duration_s": 60, "art_direction": "cinematic_story", "sources": []}}}


class TestPlanningJob(unittest.TestCase):
    def ports(self, provider, **overrides):
        saved, events = [], []
        values = dict(provider=provider, env=ENV, persist=saved.append,
                      record_event=lambda name, **props: events.append((name, props)),
                      budget=cost.Budget(1, 1))
        values.update(overrides)
        return planning_job.Ports(**values), saved, events

    def test_new_idea_reaches_model_and_produces_editable_plan(self):
        raw = copy.deepcopy(sample.moral_plan())
        raw["title"] = "Le repas de l'ancien ennemi"
        llm = FakeLLM(planner.LLMResult(json.dumps(raw), {"input": 3000, "output": 2500}))
        ports, saved, events = self.ports(llm)
        result = planning_job.run(script_for(), ports)
        self.assertIn("petit renard nourrit", llm.prompts[0])
        self.assertEqual(saved[0]["story_plan"]["title"], "Le repas de l'ancien ennemi")
        self.assertFalse(saved[0]["script_validated"])
        self.assertEqual(saved[0]["story_planning"]["state"], "completed")
        self.assertEqual(events[0][0], "story_planning_completed")
        self.assertGreater(result["cost_usd"], 0)

    def test_invalid_or_unconfirmed_request_calls_nothing(self):
        llm = FakeLLM(planner.LLMResult("{}", {"input": 1, "output": 1}))
        bad = script_for()
        bad["story_planning"]["confirmed_max_usd"] = 1.01
        with self.assertRaises(planning_job.PlanningError):
            planning_job.run(bad, self.ports(llm)[0])
        self.assertEqual(llm.prompts, [])
    def test_true_story_without_sources_is_refused_before_provider(self):
        llm = FakeLLM(planner.LLMResult("{}", {"input": 1, "output": 1}))
        bad = script_for()
        bad["story_planning"]["request"]["story_type"] = "true"
        with self.assertRaises(planning_job.PlanningError):
            planning_job.run(bad, self.ports(llm)[0])
        self.assertEqual(llm.prompts, [])

    def test_existing_plan_is_idempotent(self):
        llm = FakeLLM(planner.LLMResult("{}", {"input": 1, "output": 1}))
        ready = script_for()
        ready["story_plan"] = sample.moral_plan()
        result = planning_job.run(ready, self.ports(llm)[0])
        self.assertTrue(result["idempotent_replay"])
        self.assertEqual(llm.prompts, [])

    def test_cumulative_ledger_blocks_a_retry_that_could_cross_confirmation(self):
        class Ledger:
            def total(self): return 0.01
        llm = FakeLLM(planner.LLMResult(json.dumps(sample.moral_plan()), {"input": 1, "output": 1}))
        with self.assertRaises(planning_job.PlanningError):
            planning_job.run(script_for(), self.ports(llm, ledger=Ledger())[0])
        self.assertEqual(llm.prompts, [])


if __name__ == "__main__":
    unittest.main()
# End of offline planning-job tests.
