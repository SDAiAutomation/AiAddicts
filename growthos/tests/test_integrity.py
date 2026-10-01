"""Phase 5.3 — content-integrity detectors (engine/integrity.py) and their gate in engine/quality.py."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import integrity, quality, retention

ROOT = Path(__file__).parent.parent


def B(*texts, **extra):
    return [{"role": "point", "text": t, **extra} for t in texts]


def kinds(blocks):
    return [i["kind"] for i in integrity.find_arithmetic_inconsistencies(blocks)]


class TestArithmetic(unittest.TestCase):
    def test_weekly_times_52(self):
        # the observed Phase 5.2 error: 40 x 52 = 2,080, not 1,920
        self.assertEqual(kinds(B("Example (hypothetical): one $40 impulse per week becomes $1,920 a year.")), ["rate_conversion"])
        self.assertEqual(kinds(B("One $40 impulse per week becomes $2,080 a year.")), [])

    def test_daily_times_365_and_30(self):
        self.assertEqual(kinds(B("Five dollars a day is $150 a month and $1,825 a year, simple math.")), [])
        self.assertEqual(kinds(B("$5/day is about $1,825 a year.")), [])
        self.assertEqual(kinds(B("At $5 per day you add $1,825 a year automatically.")), [])
        self.assertEqual(kinds(B("Five dollars a day is $1,500 a year.")), ["rate_conversion"])
        self.assertEqual(kinds(B("Five dollars a day is $200 a month.")), ["rate_conversion"])

    def test_monthly_times_12(self):
        self.assertEqual(kinds(B("Automate $250 monthly, that is $3,000 a year.")), [])
        self.assertEqual(kinds(B("Automate $250 monthly, that is $2,000 a year.")), ["rate_conversion"])

    def test_time_to_goal(self):
        self.assertEqual(kinds(B("Example: $50 per week will reach $1,000 in about 20 weeks.")), [])
        self.assertEqual(kinds(B("How to reach it, save $40 a week and hit $1,000 in about 25 weeks, automatic transfer helps.")), [])
        self.assertEqual(kinds(B("Save $50 a week and you reach $1,000 in about 10 weeks.")), ["time_to_goal"])

    def test_income_minus_expenses(self):
        self.assertEqual(kinds(B("Imagine a $1,000 raise, new spending eats $850, leaving $150 extra.")), [])
        self.assertEqual(kinds(B("A $1,000 raise minus $250 rent, $180 car, $220 dining and $200 going out leaves $150.")), [])
        self.assertEqual(kinds(B("A $1,000 raise minus $250 rent, $180 car, $220 dining and $200 going out leaves $350.")), ["subtraction_chain"])

    def test_formula_scene(self):
        good = {"sceneType": "formula", "terms": ["$1,000 RAISE", "- $850 SPENT", "= $150 LEFT"]}
        bad = {"sceneType": "formula", "terms": ["$1,000 RAISE", "- $850 SPENT", "= $250 LEFT"]}
        self.assertEqual(kinds(B("x", motion_graphic=good)[:1] + []), [])
        self.assertEqual(kinds([{"role": "point", "text": "x", "motion_graphic": good}]), [])
        self.assertEqual(kinds([{"role": "point", "text": "x", "motion_graphic": bad}]), ["formula"])

    def test_sum_of_listed_amounts_and_percentage(self):
        three = "Rent adds $400. A car payment adds $300. Dining out adds $150."
        self.assertEqual(kinds(B(three, "That's $850 of new spending.")), [])
        self.assertEqual(kinds(B(three, "That's $900 of new spending.")), ["sum"])
        self.assertEqual(kinds(B("Save 50 percent of that $1,000 raise, which is $500.")), [])
        self.assertEqual(kinds(B("Save 50 percent of that $1,000 raise, which is $300.")), ["percent_of"])

    def test_simple_accumulation_without_returns(self):
        self.assertEqual(kinds(B("Five dollars a day is $1,825 a year.", "You would put in $73,000 over 40 years.")), [])
        self.assertEqual(kinds(B("Five dollars a day is $1,825 a year.", "You would put in $60,000 over 40 years.")), ["accumulation"])

    def test_unrecognized_relations_stay_silent(self):
        for text in (
            "Rent is $200 a month and coffee is $50 a week.",                    # unrelated quantities
            "If you cut $450 impulses twice a month that's $10,800 saved in a year.",  # multiplier word
            "Example, monthly income $3,000 and $200 saved, that's 50 months to $10,000.",
            "Four small buys at $45 each is $180 a month.", "Over a year, that's $2,160.",
            "Invest it yearly at an assumed 7% return: about $10,500 after five years, $25,200 after ten.",
        ):
            self.assertEqual(kinds(B(text)), [], text)
        self.assertEqual(kinds(B("Four small buys at $45 each is $180 a month, and you barely notice.", "Over a year, that's $2,160.")), [])

    def test_observed_false_positives_of_the_first_phase_53_pass(self):
        """Found by reading the detector's output on the first 15 real generations (both were CORRECT statements)."""
        # three purchases at $30 each, that's $90: a multiplication, not a sum of the previous block's amounts
        self.assertEqual(kinds(B("Example: you see a $120 gadget and wait 24 hours, you might find a $30 cheaper option.",
                                 "Small wins add up. If you postpone three impulse buys and save $30 each, that's $90 back in your pocket.")), [])
        # a per-year rate then a contribution total over N years: 1,825 x 30 = 54,750
        self.assertEqual(kinds(B("If you save $5 every day, you contribute $1,825 per year and $54,750 over 30 years.")), [])
        self.assertEqual(kinds(B("If you save $5 every day, you contribute $1,825 per year and $50,000 over 30 years.")), ["accumulation"])

    def test_never_modifies_the_script(self):
        blocks = B("One $40 impulse per week becomes $1,920 a year.")
        before = json.dumps(blocks)
        integrity.find_arithmetic_inconsistencies(blocks)
        self.assertEqual(json.dumps(blocks), before)


class TestInvestmentAssumptions(unittest.TestCase):
    def codes(self, *texts):
        return [i["kind"] for i in integrity.find_projection_issues(B(*texts))]

    def test_explicit_assumption_passes(self):
        self.assertEqual(self.codes("Invest $1,825 a year.", "At 7% annual return, hypothetically, it grows to about $172,000 in 30 years."), [])
        self.assertEqual(self.codes("Assuming a 7% annual return, $1,825 a year could be worth $172,000 in 30 years."), [])

    def test_projection_without_a_stated_rate(self):
        self.assertEqual(self.codes("Invest $1,825 a year.", "It grows to about $172,000 in 30 years."), ["rate_unstated"])

    def test_projection_not_presented_as_hypothetical(self):
        self.assertEqual(self.codes("Invest $1,825 a year.", "At 7% it grows to about $172,000 in 30 years."), ["unhedged"])

    def test_guaranteed_language(self):
        self.assertEqual(self.codes("Index funds are a guaranteed way to get rich."), ["guaranteed"])
        self.assertEqual(self.codes("This is risk-free."), ["guaranteed"])
        self.assertEqual(self.codes("Returns are not guaranteed and real returns vary."), [])

    def test_non_investing_scripts_are_untouched(self):
        self.assertEqual(self.codes("Wait 24 hours.", "In 10 years you will have saved $12,000 by skipping coffee."), [])


class TestUnsupportedClaims(unittest.TestCase):
    def flagged(self, *texts, **extra):
        return [i["phrase"] for i in integrity.find_unsupported_empirical_claims({"blocks": B(*texts), **extra})]

    def test_statistical_generalities_are_flagged(self):
        self.assertEqual(len(self.flagged("Most urges fade by morning.")), 1)
        self.assertEqual(len(self.flagged("Studies show it works.")), 1)
        self.assertEqual(len(self.flagged("80 percent of people overspend.")), 1)
        self.assertEqual(len(self.flagged("Most people keep only about $25 of that urge.")), 1)
        self.assertEqual(len(self.flagged("La plupart des gens oublient leurs abonnements.")), 1)

    def test_mechanism_and_examples_are_not_flagged(self):
        self.assertEqual(self.flagged("Waiting creates distance between the impulse and the purchase.",
                                      "Say you see a $200 gadget and wait a day.", "Most of a raise can go to rent."), [])

    def test_a_provided_source_exempts_the_script(self):
        self.assertEqual(self.flagged("Studies show it works.", source_type="pasted_text"), [])
        self.assertEqual(self.flagged("Studies show it works.", source_text="Our own survey of 200 users."), [])


class TestCtaPromises(unittest.TestCase):
    def test_bait_patterns(self):
        for text in (
            "Want a simple 30-day plan to save $1,000? Comment '30'.", "Comment \"Lock\" below and I'll send it.", "DM me for the plan.",
            "I'll send you the spreadsheet.", "Link in bio for the template.", "Want a two-line script to automate raise savings?",
            "Want a 30-day leak-fix checklist to try this month?", "Get my free checklist.", "Commente « 30 » pour recevoir le guide.",
        ):
            self.assertTrue(integrity.has_cta_promise(text), text)

    def test_honest_ctas_are_not_flagged(self):
        for text in (
            "Which subscription would you pause this month?", "Save this for the slow months.", "Try the 24-hour test this week.",
            "Where does your $5 a day go?", "Money Rule #2 is next.", "Which would you pick, 5% or 8%?",
        ):
            self.assertFalse(integrity.has_cta_promise(text), text)

    def test_only_the_closing_block_is_checked(self):
        blocks = [{"role": "hook", "text": "Want a template? Here is how."}, {"role": "point", "text": "It works."},
                  {"role": "cta", "text": "Comment '30' below."}]
        self.assertEqual(integrity.find_cta_promises(blocks), [2])


class TestPlaceholders(unittest.TestCase):
    def test_visible_placeholders(self):
        self.assertEqual(integrity.find_placeholders([["Fix three leaks, automate $X to savings"], ["Clean text"], ["$Saved", "ok"]]), [0, 2])
        self.assertEqual(integrity.find_placeholders([["automate $250", "5%"]]), [])
        self.assertEqual(integrity.find_placeholders([["example rate"]]), [0])


class TestIntegrityGate(unittest.TestCase):
    def setUp(self):
        # a plausible final file, so the gate is judged on the content signals only
        self._tmp = tempfile.TemporaryDirectory()
        self.final = Path(self._tmp.name) / "final.mp4"
        self.final.write_bytes(b"0" * 300_000)

    def tearDown(self):
        self._tmp.cleanup()

    def analyze(self, blocks, **extra):
        return retention.analyze({"title": "T", "niche": "n", "account": "a", "language": "en", "blocks": blocks, **extra})

    def score(self, report):
        return quality.score_generation({"total_duration": 30.0, "content_goal": "reach", "retention": report}, str(self.final))

    def test_blocking_codes_are_aligned_between_modules(self):
        self.assertEqual(set(quality._BLOCKING_RETENTION_CODES), set(retention.BLOCKING_CODES))

    def test_false_numbers_hold_the_video_for_review_even_without_a_strategy(self):
        blocks = [{"role": "hook", "text": "What does a habit cost?"},
                  {"role": "point", "text": "Example: one $40 impulse per week becomes $1,920 a year."}]
        report = self.analyze(blocks)
        self.assertFalse(report["hasContentStrategy"])
        self.assertIn("arithmetic_inconsistency", [i["code"] for i in report["issues"]])
        base, _ = quality.score_generation({"total_duration": 30.0, "content_goal": "reach"}, str(self.final))
        score, flags = self.score(report)
        self.assertLess(score, quality.PASS_THRESHOLD)
        self.assertGreater(base, quality.PASS_THRESHOLD)
        self.assertTrue(any(f.startswith("Intégrité du contenu") for f in flags))

    def test_each_blocking_defect_is_detected_in_a_full_analysis(self):
        cases = {
            "arithmetic_inconsistency": [{"role": "point", "text": "One $40 impulse per week becomes $1,920 a year."}],
            "projection_assumption_missing": [{"role": "point", "text": "Invest $1,825 a year."},
                                              {"role": "point", "text": "It grows to about $172,000 in 30 years."}],
            "guaranteed_language": [{"role": "point", "text": "Index funds are a guaranteed way to get rich."}],
            "role_label_leak": [{"role": "point", "text": "Pattern interrupt, some people save more."}],
            "unsupported_cta_promise": [{"role": "cta", "text": "Want a free checklist? Comment 'plan' below."}],
            "viewer_placeholder": [{"role": "point", "text": "Then automate $X to savings."}],
        }
        for code, blocks in cases.items():
            report = self.analyze([{"role": "hook", "text": "Where does it go?"}] + blocks)
            self.assertIn(code, [i["code"] for i in report["issues"]], code)
            self.assertLess(self.score(report)[0], quality.PASS_THRESHOLD, code)

    def test_clean_script_is_not_held(self):
        blocks = [{"role": "hook", "text": "Where does your raise go?"},
                  {"role": "point", "text": "Say you get a $1,000 raise and new spending eats $850, leaving $150."}]
        report = self.analyze(blocks)
        self.assertEqual([i for i in report["issues"] if i["severity"] == "high"], [])
        self.assertGreaterEqual(self.score(report)[0], quality.PASS_THRESHOLD)

    def test_scene_fallback_is_recorded_as_information_only(self):
        blocks = [{"role": "hook", "text": "Where does it go?"}, {"role": "point", "text": "Rent is $400."}]
        report = retention.analyze({"title": "T", "language": "en", "blocks": blocks},
                                   scene_reports=[{"blockIndex": 1, "sceneType": "icon_text", "action": "fallback_semantic"}])
        issue = [i for i in report["issues"] if i["code"] == "scene_data_fallback"][0]
        self.assertEqual(issue["severity"], "info")
        self.assertGreaterEqual(self.score(report)[0], quality.PASS_THRESHOLD)

    def test_legacy_scripts_are_not_flagged(self):
        paths = sorted((ROOT / "content" / "scripts").glob("*.json")) + sorted((ROOT / "content" / "scripts" / "benchmark").glob("*.json"))
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "blocks" not in data:
                continue
            integrity_issues = [i["code"] for i in retention.analyze(data)["issues"] if i["section"] == "integrity"]
            # c-explainer opens with "La plupart des gens ..." : a genuine unsourced generality, correctly reported
            expected = ["unsupported_empirical_claim"] if path.name == "c-explainer.stock_footage.json" else []
            self.assertEqual(integrity_issues, expected, path.name)

    def test_phase_52_failures_are_caught(self):
        for name in ("real_s1", "real_s2", "real_s3", "real_s4", "real_s5", "real_p5c"):
            data = json.loads((ROOT / "tests" / "fixtures" / "phase51" / f"{name}.json").read_text(encoding="utf-8"))
            report = retention.analyze(data)
            for issue in report["issues"]:
                self.assertIn(issue["severity"], ("high", "info"))
        s2 = json.loads((ROOT / "tests" / "fixtures" / "phase51" / "real_s2.json").read_text(encoding="utf-8"))
        codes = [i["code"] for i in retention.analyze(s2)["issues"]]
        self.assertIn("viewer_placeholder", codes)  # "$Saved" / "$Spent" in the compound_growth scene


if __name__ == "__main__":
    unittest.main()
