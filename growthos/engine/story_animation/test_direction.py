import json
import os
import unittest
from unittest import mock

import requests

from growthos.engine.story_animation import direction

LOOKS = {"pip": {"name": "Pip", "description": "x"}, "rosette": {"name": "Madame Rosette", "description": "y"}}
STORY = {"language": "fr", "style_id": "noir_1930", "shots": [{"dialogue": "Quelqu'un a sorti son téléphone.", "intent": "tension"}]}


def beat(i, text="Quelqu'un a sorti son téléphone.", speaker="narrator"):
    return {"index": i, "text": text, "speaker_id": speaker, "shot_index": 0, "line_first": i == 0}


def answer(rows):
    return json.dumps({"beats": rows})


GOOD = {"show": "A gloved hand pulls a shiny telephone out of a coat pocket, everyone stares.", "shot": "insert",
        "camera": "push_in", "characters": [], "crowd": ["passerby"], "section_start": False}


class Validation(unittest.TestCase):
    def test_good_row_is_kept(self):
        d, repaired = direction.validate_row({"i": 0, **GOOD}, beat(0), LOOKS)
        self.assertEqual(repaired, 0)
        self.assertEqual(d["shot"], "insert")
        self.assertEqual(d["source"], "llm")

    def test_closed_enums_and_unknown_ids_are_repaired(self):
        row = {**GOOD, "shot": "extreme_close", "camera": "dolly_zoom", "characters": ["pip", "../../etc", "pip", 3],
               "crowd": ["worker", "alien"], "section_start": "yes"}
        d, repaired = direction.validate_row(row, beat(1), LOOKS)
        self.assertIn(d["shot"], direction.SHOT_SIZES)
        self.assertIn(d["camera"], direction.CAMERA_MOVES)
        self.assertEqual(d["characters"], ["pip"])
        self.assertEqual(d["crowd"], ["worker"])
        self.assertFalse(d["section_start"])
        self.assertGreaterEqual(repaired, 4)

    def test_show_is_cleaned_and_bounded(self):
        d, _ = direction.validate_row({**GOOD, "show": "A\x00 phone\n\n" + "x" * 900}, beat(0), LOOKS)
        self.assertNotIn("\x00", d["show"])
        self.assertLessEqual(len(d["show"]), direction.SHOW_MAX)

    def test_missing_show_falls_back_deterministically(self):
        d, _ = direction.validate_row({**GOOD, "show": ""}, beat(2, speaker="pip"), LOOKS)
        self.assertEqual(d["source"], "fallback")
        self.assertEqual(d["characters"], ["pip"])
        self.assertEqual(d, direction.validate_row({"show": None}, beat(2, speaker="pip"), LOOKS)[0])

    def test_variety_is_enforced(self):
        rows = [dict(GOOD, shot="medium", camera="pan_left", section_start=True) for _ in range(6)]
        for r in rows:
            r["source"] = "llm"
        out = direction.enforce_variety(rows)
        for a, b, c in zip(out, out[1:], out[2:]):
            self.assertFalse(a["shot"] == b["shot"] == c["shot"])
        for a, b in zip(out, out[1:]):
            self.assertNotEqual(a["camera"], b["camera"])
        self.assertFalse(out[0]["section_start"])
        self.assertLessEqual(sum(d["section_start"] for d in out), 2)


class Direct(unittest.TestCase):
    def test_one_call_returns_every_beat(self):
        calls = []

        def call(messages, model):
            calls.append((messages, model))
            return answer([{"i": i, **GOOD} for i in range(3)]), {"input": 1000, "output": 300}

        res = direction.direct(STORY, [beat(i) for i in range(3)], LOOKS, call=call, model="m")
        self.assertEqual(len(calls), 1)
        self.assertEqual(res.source, "llm")
        self.assertEqual(len(res.beats), 3)
        system, user = calls[0][0][0]["content"], json.loads(calls[0][0][1]["content"])
        self.assertIn("One idea = one image", system)
        self.assertEqual(user["prompt_version"], direction.PROMPT_VERSION)
        self.assertEqual([c["id"] for c in user["characters"]], ["pip", "rosette"])

    def test_partial_answer_is_mixed(self):
        res = direction.direct(STORY, [beat(i) for i in range(3)], LOOKS,
                               call=lambda m, mo: (answer([{"i": 1, **GOOD}, {"i": 99, **GOOD}, {"i": True, **GOOD}]), {}),
                               model="m")
        self.assertEqual(res.source, "mixed")
        self.assertEqual([d["source"] for d in res.beats], ["fallback", "llm", "fallback"])

    def test_garbage_then_retry_then_fallback(self):
        seq = iter(["not json", "{\"beats\": 3}"])
        res = direction.direct(STORY, [beat(0)], LOOKS, call=lambda m, mo: (next(seq), {}), model="m")
        self.assertEqual(res.llm_calls, direction.MAX_ATTEMPTS)
        self.assertEqual(res.source, "fallback")
        self.assertEqual(len(res.errors), 2)

    def test_network_error_falls_back(self):
        def boom(m, mo):
            raise requests.ConnectionError("down")

        res = direction.direct(STORY, [beat(0), beat(1)], LOOKS, call=boom, model="m")
        self.assertEqual(res.source, "fallback")
        self.assertEqual(res.llm_calls, 2)

    def test_fenced_json_is_accepted(self):
        res = direction.direct(STORY, [beat(0)], LOOKS,
                               call=lambda m, mo: ("```json\n" + answer([{"i": 0, **GOOD}]) + "\n```", {}), model="m")
        self.assertEqual(res.source, "llm")

    def test_no_model_means_no_call(self):
        res = direction.direct(STORY, [beat(0)], LOOKS, call=None, model=None)
        self.assertEqual((res.source, res.llm_calls), ("fallback", 0))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(direction.director_model())
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=True):
            self.assertEqual(direction.director_model(), direction.DEFAULT_MODEL)

    def test_llm_cost_needs_configured_prices(self):
        usage = [{"input": 1_000_000, "output": 1_000_000}]
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(direction.llm_cost_usd(usage))
        with mock.patch.dict(os.environ, {"STORY_DIRECTOR_PRICE_IN_PER_M": "0.25", "STORY_DIRECTOR_PRICE_OUT_PER_M": "2"}):
            self.assertAlmostEqual(direction.llm_cost_usd(usage), 2.25)


if __name__ == "__main__":
    unittest.main()
