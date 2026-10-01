import ast
import copy
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import generation_cache, quality, retention, script as script_module

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "content" / "scripts"


def _block(role, text, **extra):
    return {"role": role, "text": text, **extra}


def _script(blocks, **extra):
    return {"title": "T", "niche": "n", "account": "a", "language": "en", "blocks": blocks, **extra}


def _raise_script(**overrides):
    """Un script de référence sain (hook / escalade / preuve / révélation / payoff / cta)."""
    blocks = [
        _block("hook", "You got a raise. So why are you still broke?", retentionRole="hook", informationGain="new_question"),
        _block("point", "Say your pay goes up $1,000 a month.", retentionRole="setup", informationGain="new_example"),
        _block("point", "A pricier apartment adds $400. A car payment adds $300. Dining out adds $150.",
               retentionRole="escalation", informationGain="new_example"),
        _block("point", "That is $850 of new spending every month.", retentionRole="evidence", informationGain="new_fact"),
        _block("point", "So only $150 of your raise is left.", retentionRole="reveal", informationGain="answer"),
        _block("point", "Your raise did not vanish, your spending grew to meet it. Save $500 first.",
               retentionRole="payoff", informationGain="answer"),
        _block("cta", "Rule #3 is next.", retentionRole="cta", informationGain="cta"),
    ]
    data = _script(blocks, contentStrategy={
        "coreQuestion": "Why is a raise not leaving you better off?", "hookType": "contradiction",
        "ctaIntent": "next_episode", "payoff": "A $1,000 raise left only $150 after $850 of new spending.",
    }, series={"name": "Money Rules", "episode": 2, "continuityCTA": "Rule #3 is next"})
    data.update(overrides)
    return data


def _codes(report, section=None):
    return [i["code"] for i in report["issues"] if section in (None, i["section"])]


class TestHookTypes(unittest.TestCase):
    def test_all_ten_hook_types_are_accepted(self):
        self.assertEqual(len(retention.HOOK_TYPES), 10)
        for hook_type in retention.HOOK_TYPES:
            retention.validate_content_strategy({"hookType": hook_type})

    def test_unknown_hook_type_is_rejected(self):
        with self.assertRaises(ValueError):
            retention.validate_content_strategy({"hookType": "clickbait"})

    def test_script_validation_rejects_invalid_strategy_but_not_absent_one(self):
        base = _script([_block("hook", "Never do this."), _block("cta", "Follow.")])
        script_module.validate_script(base)  # absent : OK
        bad = {**base, "contentStrategy": {"ctaIntent": "spam"}}
        with self.assertRaises(ValueError):
            script_module.validate_script(bad)
        with self.assertRaises(ValueError):
            script_module.validate_script({**base, "contentStrategy": "not an object"})

    def test_strategy_field_types(self):
        with self.assertRaises(ValueError):
            retention.validate_content_strategy({"audiencePromise": 3})
        with self.assertRaises(ValueError):
            retention.validate_content_strategy({"targetDurationSec": -5})
        with self.assertRaises(ValueError):
            retention.validate_content_strategy({"targetDurationSec": True})
        retention.validate_content_strategy({"targetDurationSec": 30})

    def test_hook_type_signal_is_reported_per_type(self):
        examples = {
            "contradiction": "You got a raise. So why are you still broke?",
            "specific_number": "$5 a day sounds small.",
            "warning": "Never do this right after a raise.",
            "scenario": "You wake up tomorrow with $10,000.",
            "comparison": "Two people earn the same salary. Only one gets wealthy.",
            "mistake": "The biggest money mistake nobody mentions.",
            "curiosity_gap": "Why is your first $10,000 so hard?",
        }
        for hook_type, text in examples.items():
            diag = retention.diagnose_hook(text, hook_type)
            self.assertTrue(diag["hookTypeSignal"], f"{hook_type}: {text}")
        weak = retention.diagnose_hook("Money is a thing people use.", "specific_number")
        self.assertFalse(weak["hookTypeSignal"])
        # Phase 5.2 : le type est une métadonnée d'analyse, jamais un défaut du hook.
        self.assertNotIn("hook_type_signal_missing", [i["code"] for i in weak["issues"]])


class TestHookDiagnostics(unittest.TestCase):
    def test_generic_openings_are_detected_in_several_languages(self):
        for text in (
            "Did you know that saving matters?", "Have you ever wondered where your money goes?",
            "In today's video we look at budgets.", "Let's talk about money.", "Managing money can be difficult.",
            "Here are some tips for saving.", "Saviez-vous que l'épargne compte ?", "Dans cette vidéo, on parle d'argent.",
        ):
            diag = retention.diagnose_hook(text)
            self.assertTrue(diag["genericOpening"], text)
            self.assertIn("generic_opening", [i["code"] for i in diag["issues"]])

    def test_strong_hook_has_no_issue_and_matches_the_documented_shape(self):
        diag = retention.diagnose_hook("$5 a day sounds small. Do it for 20 years.")
        self.assertFalse(diag["genericOpening"])
        self.assertTrue(diag["containsSpecificNumber"])
        self.assertTrue(diag["tensionDetected"] or diag["containsSpecificNumber"])
        self.assertFalse(diag["delayedValue"])
        self.assertEqual(diag["issues"], [])
        for key in ("wordCount", "genericOpening", "containsSpecificNumber", "tensionDetected", "delayedValue", "issues"):
            self.assertIn(key, diag)

    def test_hook_length_is_configurable(self):
        long_hook = "You got a raise last year and then another one this year so why are you still broke today"
        self.assertIn("hook_too_long", [i["code"] for i in retention.diagnose_hook(long_hook)["issues"]])
        relaxed = retention.RetentionConfig(hook_max_words=40)
        self.assertNotIn("hook_too_long", [i["code"] for i in retention.diagnose_hook(long_hook, config=relaxed)["issues"]])
        self.assertEqual(retention.diagnose_hook("One two three")["wordCount"], 3)

    def test_delayed_value_and_no_tension(self):
        slow = retention.diagnose_hook("Managing a household budget carefully every single month requires 3 habits")
        self.assertTrue(slow["delayedValue"])
        flat = retention.diagnose_hook("People use banks for their accounts.")
        self.assertFalse(flat["tensionDetected"])
        # Phase 5.2 : l'absence de tension est une mesure, pas un défaut (un hook calme peut fonctionner).
        self.assertNotIn("no_tension", [i["code"] for i in flat["issues"]])
        # une valeur « tardive » ne se signale que sur un hook long
        short = retention.diagnose_hook("Invest five dollars a day, watch what happens.")
        self.assertFalse(short["delayedValue"])

    def test_hook_repeating_the_title_is_flagged(self):
        diag = retention.diagnose_hook("Lifestyle inflation", title="Lifestyle inflation")
        self.assertTrue(diag["repeatsTitle"])
        diag = retention.diagnose_hook("Lifestyle inflation ate your $850 raise", title="Lifestyle inflation")
        self.assertFalse(diag["repeatsTitle"])

    def test_missing_hook(self):
        self.assertIn("hook_missing", [i["code"] for i in retention.diagnose_hook("")["issues"]])


class TestRetentionRoles(unittest.TestCase):
    def test_block_role_validation(self):
        retention.validate_block_retention({"retentionRole": "pattern_interrupt", "informationGain": "new_fact"}, 0)
        with self.assertRaises(ValueError):
            retention.validate_block_retention({"retentionRole": "filler"}, 0)
        with self.assertRaises(ValueError):
            retention.validate_block_retention({"informationGain": "vibes"}, 0)
        bad = _script([_block("hook", "Never do this.", retentionRole="nope"), _block("cta", "Follow.")])
        with self.assertRaises(ValueError):
            script_module.validate_script(bad)

    def test_roles_are_declared_then_mapped_from_visual_purpose(self):
        blocks = [
            _block("hook", "h"), _block("point", "a", visualPurpose="establish"),
            _block("point", "b", visualPurpose="action"), _block("point", "c", visualPurpose="explain"),
            _block("point", "d", retentionRole="reveal", visualPurpose="explain"), _block("cta", "z"),
        ]
        roles = retention.assign_retention_roles(blocks)
        self.assertEqual([r["role"] for r in roles], ["hook", "setup", "escalation", None, "reveal", "cta"])
        self.assertEqual(roles[4]["source"], "declared")
        self.assertEqual(roles[3]["source"], "unassigned")

    def test_explanation_run_is_flagged(self):
        blocks = [_block("hook", "Why does this happen to you?", retentionRole="hook")]
        blocks += [_block("point", f"Explanation number {i} about a topic", retentionRole="setup") for i in range(4)]
        blocks += [_block("point", "Done", retentionRole="payoff"), _block("cta", "Follow", retentionRole="cta")]
        report = retention.analyze(_script(blocks))
        self.assertIn("explanation_run", _codes(report, "structure"))

    def test_progression_with_escalation_and_reveal_has_no_structure_issue(self):
        report = retention.analyze(_raise_script())
        self.assertEqual(_codes(report, "structure"), [])
        self.assertEqual(report["structure"]["sequence"][0], "hook")
        self.assertEqual(report["structure"]["sequence"][-1], "cta")

    def test_no_role_sequence_is_mandatory(self):
        """Les rôles sont des outils : aucun rôle manquant ni ordre ne produit de défaut."""
        sequences = [
            ["hook", "evidence", "payoff"],
            ["hook", "evidence", "reveal", "payoff"],
            ["hook", "setup", "evidence", "payoff", "cta"],
            ["hook", "payoff"],
            ["hook", "setup", "evidence"],  # même sans reveal/payoff déclaré
            ["hook", "reveal", "setup", "evidence"],  # une mise en contexte après la réponse reste légitime
        ]
        for seq in sequences:
            blocks = [_block("hook" if r == "hook" else "cta" if r == "cta" else "point", f"unique content number {i} about topic {i}", retentionRole=r)
                      for i, r in enumerate(seq)]
            self.assertEqual(_codes(retention.analyze(_script(blocks)), "structure"), [], seq)

    def test_scripts_without_any_role_information_get_no_structure_issue(self):
        blocks = [_block("hook", "Why does it happen?")] + [_block("point", f"point {i}") for i in range(5)] + [_block("cta", "Follow")]
        structure = retention.analyze(_script(blocks))["structure"]
        self.assertFalse(structure["available"])
        self.assertEqual(structure["issues"], [])


class TestOpenLoops(unittest.TestCase):
    def test_resolved_loop_reports_delay(self):
        data = _raise_script(openLoops=[{"question": "Why is a raise not leaving you better off?",
                                         "openedAtBlock": 0, "resolvedAtBlock": 4}])
        report = retention.analyze(data)
        loop = report["openLoops"][0]
        self.assertEqual(loop["status"], "resolved")
        self.assertEqual(loop["delayBlocks"], 4)
        self.assertGreater(loop["delaySec"], 0)
        self.assertEqual(_codes(report, "openLoops"), [])

    def test_single_open_loop_form_from_the_spec_is_accepted(self):
        data = _raise_script(openLoop={"question": "Where did the extra $1,000 go?", "openedAtBlock": 0, "resolvedAtBlock": 5})
        script_module.validate_script(data)
        self.assertEqual(len(retention.analyze(data)["openLoops"]), 1)

    def test_unresolved_loop_is_flagged_not_rejected(self):
        data = _raise_script(openLoops=[{"question": "Where did the raise go?", "openedAtBlock": 0}])
        script_module.validate_script(data)
        self.assertIn("unresolved_loop", _codes(retention.analyze(data), "openLoops"))

    def test_loop_resolved_by_the_cta_or_before_opening(self):
        data = _raise_script(openLoops=[{"question": "Where did the raise go?", "openedAtBlock": 0, "resolvedAtBlock": 6}])
        self.assertIn("resolved_by_cta", _codes(retention.analyze(data), "openLoops"))
        data = _raise_script(openLoops=[{"question": "Where did the raise go?", "openedAtBlock": 3, "resolvedAtBlock": 1}])
        self.assertIn("loop_resolved_before_opened", _codes(retention.analyze(data), "openLoops"))

    def test_loop_indices_must_be_valid_blocks(self):
        data = _raise_script(openLoops=[{"question": "q?", "openedAtBlock": 0, "resolvedAtBlock": 99}])
        with self.assertRaises(ValueError):
            script_module.validate_script(data)
        with self.assertRaises(ValueError):
            script_module.validate_script(_raise_script(openLoops=[{"openedAtBlock": 0}]))

    def test_implicit_loop_from_core_question(self):
        report = retention.analyze(_raise_script())
        self.assertFalse(report["openLoops"][0]["declared"])
        self.assertEqual(report["openLoops"][0]["status"], "resolved")

    def test_open_loops_are_optional(self):
        data = _script([_block("hook", "Why?"), _block("point", "x y z")],
                       contentStrategy={"hookType": "curiosity_gap"}, openLoops=[])
        script_module.validate_script(data)
        self.assertEqual(_codes(retention.analyze(data), "openLoops"), [])

    def test_unresolved_promise_is_detected(self):
        blocks = [
            _block("hook", "Stay until the end to see the trick.", retentionRole="hook"),
            _block("point", "Banks make money from fees, simply put.", retentionRole="setup"),
            _block("cta", "Follow us.", retentionRole="cta"),
        ]
        report = retention.analyze(_script(blocks))
        self.assertTrue(report["promises"])
        self.assertIn("promise_without_resolution", _codes(report, "openLoops"))


class TestInformationProgression(unittest.TestCase):
    def test_new_numbers_and_novelty_are_tracked(self):
        report = retention.analyze(_raise_script())
        per_block = {entry["block"]: entry for entry in report["repetition"]["perBlock"]}
        self.assertIn("850", per_block[3]["newNumbers"])
        self.assertGreater(per_block[2]["novelTokenRatio"], 0.5)
        self.assertEqual(report["repetition"]["declaredGainCount"], 7)

    def test_repeated_block_is_detected(self):
        blocks = [
            _block("hook", "Why are you always broke?"),
            _block("point", "Spending quietly grows whenever your income grows every year."),
            _block("point", "Your income grows every year and spending quietly grows with it."),
            _block("point", "Whenever income grows every year, spending quietly grows too."),
            _block("cta", "Follow."),
        ]
        codes = _codes(retention.analyze(_script(blocks)), "repetition")
        self.assertIn("near_duplicate", codes)
        self.assertIn("repeats_earlier", codes)

    def test_a_block_with_a_new_number_is_not_a_repeat(self):
        blocks = [
            _block("hook", "Why are you always broke?"),
            _block("point", "Spending quietly grows whenever your income grows every year."),
            _block("point", "Spending quietly grows whenever your income grows, about 12 percent."),
            _block("cta", "Follow."),
        ]
        self.assertNotIn("repeats_earlier", _codes(retention.analyze(_script(blocks)), "repetition"))

    def test_reveal_may_recombine_earlier_terms(self):
        self.assertNotIn("repeats_earlier", _codes(retention.analyze(_raise_script()), "repetition"))


class TestPayoff(unittest.TestCase):
    def test_bad_payoff_from_the_spec_is_flagged(self):
        blocks = [
            _block("hook", "Here's why your raise disappears.", retentionRole="hook"),
            _block("point", "Spending grows with income, in many households.", retentionRole="evidence"),
            _block("point", "Be smarter with money.", retentionRole="payoff"),
            _block("cta", "Follow.", retentionRole="cta"),
        ]
        data = _script(blocks, contentStrategy={"coreQuestion": "Why does your raise disappear?"})
        codes = _codes(retention.analyze(data), "payoff")
        self.assertIn("generic_payoff", codes)
        self.assertIn("payoff_not_resolving_hook", codes)

    def test_good_payoff_from_the_spec_resolves_the_hook(self):
        blocks = [
            _block("hook", "Here's why your raise disappears.", retentionRole="hook"),
            _block("point", "Spending grows with income, in many households.", retentionRole="evidence"),
            _block("point", "Your fixed lifestyle expanded by $850, leaving only $150 of the $1,000 raise.", retentionRole="payoff"),
            _block("cta", "Follow.", retentionRole="cta"),
        ]
        data = _script(blocks, contentStrategy={"coreQuestion": "Why does your raise disappear?"})
        payoff = retention.analyze(data)["payoff"]
        self.assertTrue(payoff["resolvesHook"])
        self.assertTrue(payoff["concreteValue"])
        self.assertEqual(payoff["issues"], [])

    def test_promised_numbers_must_appear_in_the_script(self):
        data = _raise_script()
        data["contentStrategy"]["payoff"] = "The raise left only $175 after spending."
        self.assertIn("promised_number_missing", _codes(retention.analyze(data), "payoff"))

    def test_cta_must_not_replace_the_payoff(self):
        blocks = [_block("hook", "Why are you broke?", retentionRole="hook"),
                  _block("cta", "Because you spend $850 on lifestyle upgrades.", retentionRole="cta")]
        self.assertIn("cta_replaces_payoff", _codes(retention.analyze(_script(blocks)), "payoff"))

    def test_payoff_missing_when_there_is_no_body(self):
        report = retention.analyze(_script([_block("hook", "Why?")]))
        self.assertIn("payoff_missing", _codes(report, "payoff"))

    def test_weak_overlap_without_core_question_is_informational_only(self):
        blocks = [_block("hook", "Nour found a broken music box."), _block("point", "Dust everywhere around."),
                  _block("point", "A photo of a family appeared.", retentionRole="reveal"), _block("cta", "Open it?")]
        issues = [i for i in retention.analyze(_script(blocks))["issues"] if i["code"] == "payoff_not_resolving_hook"]
        for issue in issues:
            self.assertEqual(issue["severity"], "info")


class TestCta(unittest.TestCase):
    def test_all_cta_intents_are_accepted(self):
        self.assertEqual(
            set(retention.CTA_INTENTS),
            {"none", "follow_for_series", "question", "next_episode", "save", "share", "subscribe"},
        )
        for intent in retention.CTA_INTENTS:
            retention.validate_content_strategy({"ctaIntent": intent})

    def test_intent_detection(self):
        self.assertEqual(retention.detect_cta_intent("Money Rule #2 is next."), "next_episode")
        self.assertEqual(retention.detect_cta_intent("Follow PocketLogic for one money rule a day."), "follow_for_series")
        self.assertEqual(retention.detect_cta_intent("Save this for later."), "save")
        self.assertEqual(retention.detect_cta_intent("Where does your $5 go?"), "question")
        self.assertEqual(retention.detect_cta_intent("Subscribe for more."), "subscribe")
        self.assertEqual(retention.detect_cta_intent(""), "none")

    def test_boilerplate_cta_is_flagged_unless_subscribe_is_the_intent(self):
        data = _raise_script()
        data["blocks"][-1]["text"] = "Like and subscribe for more!"
        self.assertIn("boilerplate_cta", _codes(retention.analyze(data), "cta"))
        data["contentStrategy"]["ctaIntent"] = "subscribe"
        self.assertNotIn("boilerplate_cta", _codes(retention.analyze(data), "cta"))

    def test_none_intent_with_a_cta_and_length(self):
        data = _raise_script()
        data["contentStrategy"]["ctaIntent"] = "none"
        # Phase 5.2 : écart de métadonnées, jamais un défaut visible.
        self.assertNotIn("cta_present_despite_none", _codes(retention.analyze(data), "cta"))
        data = _raise_script()
        data["blocks"][-1]["text"] = "Follow us for one more simple money rule every single day of the week please"
        self.assertIn("cta_too_long", _codes(retention.analyze(data), "cta"))

    def test_next_episode_requires_series_metadata(self):
        data = _raise_script()
        del data["series"]
        self.assertIn("next_episode_without_series", _codes(retention.analyze(data), "cta"))

    def test_no_cta_is_appended_by_the_engine(self):
        data = _script([_block("hook", "Never do this."), _block("point", "Because it costs you $50.")])
        script_module.validate_script(data)
        report = retention.analyze(data)
        self.assertEqual(report["cta"]["text"], "")
        self.assertEqual(report["cta"]["detectedIntent"], "none")


class TestSeries(unittest.TestCase):
    def test_series_is_optional_and_validated(self):
        script_module.validate_script(_raise_script())
        no_series = _raise_script()
        del no_series["series"]
        script_module.validate_script(no_series)
        for bad in ({"episode": 1}, {"name": "x", "episode": 0}, {"name": "x", "episode": "3"},
                    {"name": "x", "continuityCTA": 3}, "series"):
            with self.assertRaises(ValueError):
                retention.validate_series(bad)
        retention.validate_series({"name": "Money Rules", "episode": 3, "continuityCTA": "Follow for Rule #4"})

    def test_series_is_reported_in_the_cta_section_and_metadata(self):
        report = retention.analyze(_raise_script())
        self.assertEqual(report["cta"]["series"]["episode"], 2)
        meta = retention.build_generation_metadata(_raise_script(), report)
        self.assertEqual(meta["series"], {"name": "Money Rules", "episode": 2})


class TestVisualProgression(unittest.TestCase):
    def _mg(self, scene, **extra):
        return {"sceneType": scene, **extra}

    def test_same_visual_structure_run_is_flagged(self):
        blocks = [_block("hook", "a", motion_graphic=self._mg("big_number", displayValue="$1"))]
        blocks += [_block("point", f"b{i}", motion_graphic=self._mg("icon_text", text="x")) for i in range(3)]
        blocks += [_block("cta", "z", motion_graphic=self._mg("icon_text", text="x"))]
        self.assertIn("same_visual_structure", _codes(retention.analyze(_script(blocks)), "visualProgression"))

    def test_independent_number_slides_suggest_a_state_change(self):
        blocks = [_block("hook", "a", motion_graphic=self._mg("warning", title="t"))]
        blocks += [_block("point", f"b{i}", motion_graphic=self._mg("big_number", displayValue=f"${i}")) for i in range(1, 4)]
        blocks += [_block("cta", "z", motion_graphic=self._mg("icon_text", text="x"))]
        self.assertIn("independent_number_slides", _codes(retention.analyze(_script(blocks)), "visualProgression"))

    def test_hook_and_cta_visual_roles(self):
        blocks = [
            _block("hook", "a", retentionRole="hook", motion_graphic=self._mg("icon_text", text="x")),
            _block("point", "b", retentionRole="reveal", motion_graphic=self._mg("big_number", displayValue="$1")),
            _block("cta", "z", retentionRole="cta", motion_graphic=self._mg("bar_chart", data=[{"label": "a", "value": 1}])),
        ]
        codes = _codes(retention.analyze(_script(blocks)), "visualProgression")
        self.assertNotIn("weak_hook_visual", codes)  # jugement de goût : retiré en Phase 5.2
        self.assertIn("heavy_cta_visual", codes)

    def test_plan_and_pattern_interrupts_are_deterministic(self):
        data = _raise_script()
        for b, scene in zip(data["blocks"], ["big_number", "icon_text", "bar_chart", "big_number", "money_split", "formula", "icon_text"]):
            b["motion_graphic"] = self._mg(scene)
        first = retention.analyze(copy.deepcopy(data))["visualProgression"]
        second = retention.analyze(copy.deepcopy(data))["visualProgression"]
        self.assertEqual(first, second)
        self.assertEqual(first["plan"][2]["role"], "escalation")
        self.assertIn("bar_chart", first["plan"][2]["preferredScenes"])
        self.assertEqual(first["patternInterrupts"][4]["interrupt"], "chart_appearance")
        self.assertEqual(first["patternInterrupts"][3]["interrupt"], "number_reveal")

    def test_stagnant_run_gets_a_suggestion_without_inventing_effects(self):
        blocks = [_block("hook", "a", shotType="close_up")] + [_block("point", f"b{i}", shotType="medium") for i in range(4)]
        plan = retention.plan_pattern_interrupts(blocks, retention.assign_retention_roles(blocks))
        self.assertEqual(plan[1]["interrupt"], "framing_change")
        self.assertTrue(any(p["suggestion"] for p in plan[3:]))

    def test_not_available_without_any_visual_information(self):
        report = retention.analyze(_script([_block("hook", "Why?"), _block("point", "x y z"), _block("cta", "Go")]))
        self.assertFalse(report["visualProgression"]["available"])


class TestPacing(unittest.TestCase):
    def test_estimated_and_measured_durations(self):
        data = _raise_script()
        estimated = retention.analyze(data)["pacing"]
        self.assertEqual(estimated["durationSource"], "estimated")
        measured = retention.analyze(data, durations=[3, 4, 5, 4, 3, 6, 2])["pacing"]
        self.assertEqual(measured["durationSource"], "measured")
        self.assertEqual(measured["totalSec"], 27.0)
        self.assertEqual(measured["hookSec"], 3.0)
        self.assertEqual(measured["longestBlock"], {"block": 5, "sec": 6.0})
        self.assertEqual(measured["secondsBeforePayoff"], 19.0)

    def test_hook_over_the_configured_limit_is_the_only_default_pacing_flag(self):
        slow = retention.analyze(_raise_script(), durations=[6, 4, 5, 4, 3, 6, 2])["pacing"]
        self.assertEqual([i["code"] for i in slow["issues"]], ["hook_slow"])
        self.assertIn("5.0", "".join(retention.analyze(_raise_script(), durations=[5.0, 4, 5, 4, 3, 6, 2])["summary"]))

    def test_thresholds_are_configurable_and_off_by_default(self):
        cfg = retention.RetentionConfig(max_block_sec=5.0, max_seconds_before_payoff=10.0, max_seconds_before_first_example=1.0)
        report = retention.analyze(_raise_script(), durations=[3, 4, 6, 4, 3, 6, 2], config=cfg)
        codes = [i["code"] for i in report["pacing"]["issues"]]
        self.assertIn("block_too_long", codes)
        self.assertIn("payoff_late", codes)
        self.assertIn("example_late", codes)
        self.assertEqual([i["code"] for i in retention.analyze(_raise_script(), durations=[3, 4, 6, 4, 3, 6, 2])["pacing"]["issues"]], [])

    def test_language_changes_the_estimate(self):
        text = " ".join(["word"] * 100)
        fr = retention.analyze(_script([_block("hook", text)], language="fr"))["pacing"]["totalSec"]
        en = retention.analyze(_script([_block("hook", text)], language="en"))["pacing"]["totalSec"]
        self.assertLess(fr, en)

    def test_target_duration_is_descriptive(self):
        data = _raise_script()
        data["contentStrategy"]["targetDurationSec"] = 30
        pacing = retention.analyze(data)["pacing"]
        self.assertEqual(pacing["targetDurationSec"], 30.0)
        self.assertIsNotNone(pacing["deltaFromTargetSec"])
        self.assertEqual([i for i in pacing["issues"] if i["code"] != "hook_slow"], [])


class TestLegacyCompatibility(unittest.TestCase):
    def test_every_existing_script_still_validates_and_analyzes(self):
        paths = sorted(SCRIPTS.glob("*.json")) + sorted((SCRIPTS / "benchmark").glob("*.json"))
        self.assertGreater(len(paths), 5)
        for path in paths:
            data = script_module.normalize_script(json.loads(path.read_text(encoding="utf-8")))
            script_module.validate_script(data)
            report = retention.analyze(data)
            self.assertFalse(report["hasContentStrategy"], path.name)
            self.assertEqual(report["version"], retention.VERSION)

    def test_legacy_script_is_never_penalized_by_the_quality_gate(self):
        path = SCRIPTS / "benchmark" / "a-storytelling.base.json"
        data = script_module.validate_script(json.loads(path.read_text(encoding="utf-8"))) or json.loads(path.read_text(encoding="utf-8"))
        report = retention.analyze(data)
        self.assertTrue(report["issues"])  # des diagnostics existent...
        metrics = {"total_duration": 30.0, "content_goal": "reach", "retention": report}
        baseline_score, _ = quality.score_generation({"total_duration": 30.0, "content_goal": "reach"}, "missing.mp4")
        score, flags = quality.score_generation(metrics, "missing.mp4")
        self.assertEqual(score, baseline_score)  # ...mais aucune pénalité sans contentStrategy
        self.assertFalse([f for f in flags if f.startswith("Rétention")])

    def test_scripts_without_strategy_have_no_open_loop_or_strategy_requirement(self):
        data = _script([_block("hook", "Never do this."), _block("point", "It costs $50 a year."), _block("cta", "Follow.")])
        script_module.validate_script(data)
        report = retention.analyze(data)
        self.assertFalse(report["hasContentStrategy"])
        self.assertEqual(report["openLoops"], [])

    def test_quality_gate_penalty_is_capped_and_only_with_a_strategy(self):
        data = _raise_script()
        data["blocks"][5]["text"] = "Be smarter with money."
        data["openLoops"] = [{"question": "Where?", "openedAtBlock": 0}, {"question": "Why?", "openedAtBlock": 1}]  # never resolved
        report = retention.analyze(data)
        high = [i for i in report["issues"] if i["severity"] == "high"]
        self.assertGreaterEqual(len(high), 3)
        base, _ = quality.score_generation({"total_duration": 30.0, "content_goal": "reach"}, "missing.mp4")
        score, flags = quality.score_generation({"total_duration": 30.0, "content_goal": "reach", "retention": report}, "missing.mp4")
        self.assertEqual(base - score, 12)
        self.assertTrue(any(f.startswith("Rétention") for f in flags))

    def test_derived_fields_do_not_change_the_cache_fingerprint(self):
        data = _raise_script()
        before = generation_cache.fingerprint(data, "voice")
        data["retentionDiagnostics"] = retention.analyze(data)
        data["generationMetadata"] = retention.build_generation_metadata(data)
        self.assertEqual(generation_cache.fingerprint(data, "voice"), before)

    def test_existing_derived_fields_do_not_break_validation_or_analysis(self):
        data = _raise_script()
        data["retentionDiagnostics"] = {"stale": True}
        script_module.validate_script(data)
        self.assertNotIn("stale", retention.analyze(data))


class TestAnalyticsReadyMetadata(unittest.TestCase):
    def test_generation_metadata_links_strategy_structure_and_scenes(self):
        data = _raise_script()
        for b in data["blocks"]:
            b["motion_graphic"] = {"sceneType": "big_number"}
        meta = retention.build_generation_metadata(data)
        self.assertEqual(meta["hookType"], "contradiction")
        self.assertEqual(meta["ctaIntent"], "next_episode")
        self.assertEqual(meta["narrativeStructure"][0], "hook")
        self.assertEqual(len(meta["sceneTypes"]), 7)
        self.assertEqual(meta["nBlocks"], 7)
        self.assertEqual(meta["retentionEngineVersion"], retention.VERSION)
        self.assertGreater(meta["durationSec"], 0)
        json.dumps(meta)  # sérialisable en jsonb
        json.dumps(retention.analyze(data))  # le rapport complet est écrit dans script (jsonb)

    def test_views_and_engaged_views_stay_distinct(self):
        fields = retention.OBSERVED_METRIC_FIELDS
        self.assertIn("views", fields)
        self.assertIn("engagedViews", fields)
        for name in ("shownInFeed", "choseToView", "swipedAway", "averageViewDuration",
                     "averagePercentageViewed", "likes", "comments", "shares", "subscribersGained"):
            self.assertIn(name, fields)
        joined = retention.join_observation({"hookType": "warning"}, {"views": 10, "engagedViews": 4})
        self.assertEqual(joined["observed"]["views"], 10)
        self.assertEqual(joined["observed"]["engagedViews"], 4)
        self.assertIsNone(joined["observed"]["likes"])
        with self.assertRaises(ValueError):
            retention.join_observation({}, {"viralProbability": 0.9})

    def test_nothing_is_persisted_or_fetched_by_the_engine(self):
        self.assertEqual(set(retention.empty_observed_metrics().values()), {None})


def _walk(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield f"{path}/{key}", key
            yield from _walk(item, f"{path}/{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _walk(item, f"{path}[{i}]")
    elif isinstance(value, str):
        yield path, value


class TestNoFakeViralityAndNoCost(unittest.TestCase):
    def test_reports_contain_no_viral_score_or_probability(self):
        reports = [retention.analyze(_raise_script())]
        for path in sorted((SCRIPTS / "pocketlogic").glob("*.json")):
            reports.append(retention.analyze(json.loads(path.read_text(encoding="utf-8"))))
        for report in reports:
            meta = retention.build_generation_metadata(_raise_script(), report)
            for _, text in list(_walk(report)) + list(_walk(meta)):
                lowered = text.lower()
                for banned in ("viral", "probab", "chance of going", "% chance"):
                    self.assertNotIn(banned, lowered)
            self.assertNotIn("score", report)
            self.assertNotIn("viralScore", report)

    def test_module_has_no_network_or_llm_dependency(self):
        tree = ast.parse((ROOT / "engine" / "retention.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"openai", "anthropic", "requests", "httpx", "urllib", "socket", "elevenlabs", "supabase"})
        self.assertEqual(imported - {"__future__", "re", "dataclasses"}, set())

    def test_analysis_makes_no_network_call_and_is_deterministic(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("l'analyse de rétention ne doit faire aucun appel réseau")

        data = _raise_script()
        with mock.patch.object(socket, "socket", forbidden), mock.patch.object(socket, "create_connection", forbidden):
            first = retention.analyze(copy.deepcopy(data))
            second = retention.analyze(copy.deepcopy(data))
            for path in (SCRIPTS / "pocketlogic").glob("*.json"):
                retention.analyze(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(first, second)

    def test_assembler_adds_only_local_analysis_calls(self):
        source = (ROOT / "engine" / "assembler.py").read_text(encoding="utf-8")
        self.assertIn("retention.analyze(data, durations=durations, scene_reports=motion_preflight)", source)
        # une seule analyse par génération, hors de toute boucle par bloc
        self.assertEqual(source.count("retention.analyze("), 1)


class TestBenchmarkAssets(unittest.TestCase):
    def test_five_pocketlogic_concepts_are_complete_and_clean(self):
        paths = sorted((SCRIPTS / "pocketlogic").glob("*.json"))
        self.assertGreaterEqual(len(paths), 5)
        hook_types = set()
        for path in paths:
            data = script_module.normalize_script(json.loads(path.read_text(encoding="utf-8")))
            script_module.validate_script(data)
            cs = data["contentStrategy"]
            for field in ("audiencePromise", "coreQuestion", "viewerProblem", "payoff", "hookType", "hookText",
                          "curiosityMechanism", "emotionalDriver", "targetDurationSec", "ctaIntent"):
                self.assertIn(field, cs, f"{path.name}: {field}")
            hook_types.add(cs["hookType"])
            self.assertTrue(data["openLoops"], path.name)
            report = retention.analyze(data)
            self.assertEqual([i for i in report["issues"] if i["severity"] == "high"], [], path.name)
            self.assertEqual(report["structure"]["sequence"][0], "hook")
            self.assertEqual(report["structure"]["sequence"][-1], "cta")
            self.assertTrue(all(l["status"] == "resolved" for l in report["openLoops"]), path.name)
            self.assertEqual(report["hook"]["issues"] and [i for i in report["hook"]["issues"] if i["code"] != "repeats_title"], [])
        self.assertGreaterEqual(len(hook_types), 4)

    def test_pocketlogic_scenes_pass_the_motion_graphics_layout_preflight(self):
        from engine.motion_graphics import preflight
        from engine.motion_graphics.display_text import viewer_scene
        from engine.motion_graphics.theme import resolve_theme

        theme = resolve_theme(None)
        for path in sorted((SCRIPTS / "pocketlogic").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for i, block in enumerate(data["blocks"]):
                result = preflight.check_scene(viewer_scene(block["motion_graphic"]), theme, (1080, 1920))
                self.assertTrue(result["ok"], f"{path.name} bloc {i + 1}: {result['errors']}")

    def test_series_cta_matches_intents_in_the_benchmark(self):
        data = json.loads((SCRIPTS / "pocketlogic" / "03-24-hour-rule.json").read_text(encoding="utf-8"))
        self.assertEqual(data["series"]["continuityCTA"], "Follow for Rule #4")
        self.assertEqual(data["contentStrategy"]["ctaIntent"], "follow_for_series")

    def test_before_after_report_is_reproducible_and_honest(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import retention_benchmark

        report = retention_benchmark.render_report()
        self.assertEqual(report, (SCRIPTS / "retention" / "BENCHMARK.md").read_text(encoding="utf-8"))
        self.assertIn("pas une sortie du LLM", report)
        self.assertNotIn("probab", report.lower())
        self.assertNotRegex(report.lower(), r"\d+\s*%.*viral|viral\w*\s*[:=]\s*\d")


if __name__ == "__main__":
    unittest.main()
