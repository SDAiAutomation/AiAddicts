"""Phase 5.2 — calibration regressions.

Fixtures in tests/fixtures/phase51/ are the UNTOUCHED real gpt-5-mini outputs of Phase 5.1 (stored scripts).
Tests assert GENERAL rules (what a diagnostic may claim), never that a specific example "turns green".
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import retention, script as script_module
from engine.motion_graphics import layout, scenes, semantic
from engine.motion_graphics.theme import resolve_theme

FIX = Path(__file__).parent / "fixtures" / "phase51"


def real(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def _b(role, text, **extra):
    return {"role": role, "text": text, **extra}


def _script(blocks, **extra):
    return {"title": "T", "niche": "n", "account": "a", "language": "en", "blocks": blocks, **extra}


def _codes(report, section=None):
    return [i["code"] for i in report["issues"] if section in (None, i["section"])]


# Codes autorisés à la sévérité « high » : chacun repose sur un signal STRUCTUREL ou numérique fiable,
# jamais sur un recouvrement lexical, un goût ou une liste de mots-clés.
HIGH_CONFIDENCE = {
    "hook_missing", "generic_opening", "payoff_missing", "generic_payoff",
    "unresolved_loop", "loop_resolved_before_opened", "resolved_by_cta", "cta_replaces_payoff",
    "role_label_leak", "unsupported_first_person", "repeats_earlier", "near_duplicate", "promise_without_resolution",
    # Phase 5.3 : intégrité du contenu (formes reconnues sans ambiguïté)
    "arithmetic_inconsistency", "projection_assumption_missing", "guaranteed_language", "unsupported_empirical_claim",
    "unsupported_cta_promise", "viewer_placeholder",
}
# Retirés en Phase 5.2 (faux positifs / jugements de goût mesurés en validation réelle).
RETIRED = {
    "weak_hook_visual", "hook_type_signal_missing", "cta_carries_value", "loop_resolved_after_payoff",
    "no_tension", "no_open_loop", "no_reveal_or_payoff", "no_escalation_or_evidence", "late_setup",
}


class TestRoleLabelLeakage(unittest.TestCase):
    PHASE_51_LEAKS = [
        "Pattern interrupt, some people actually save more after a raise. What's different is one habit.",
        "Reveal, the real reason you're broke after a raise is not the raise. It's the shift in choices.",
        "Resolution, make one rule. Automate a part of every raise to savings or debt paydown.",
        "Pattern interrupt, the next day the urge is weaker and you spot cheaper or better options.",
        "Relance. Compound interest turns repeated tiny deposits into something much larger.",
        # seen in the first Phase 5.2 calibration runs (prompt vocabulary spoken aloud)
        "Answer first, lifestyle inflation ate most of that extra cash.",
        "Concrete payoff, imagine a $600 impulse buy that becomes a $150 planned buy.",
        "Practical payoff, automate $300 monthly to a separate account.",
    ]

    def test_exact_phase_51_leaks_are_detected(self):
        for text in self.PHASE_51_LEAKS:
            self.assertEqual(retention.find_role_label_leaks([_b("point", text)]), [0], text)

    def test_leak_is_detected_after_a_sentence_boundary_and_in_viewer_text(self):
        self.assertEqual(retention.find_role_label_leaks([_b("point", "First test. Pattern interrupt, the urge fades.")]), [0])
        mg = {"sceneType": "icon_text", "text": "Reveal: the real reason"}
        self.assertEqual(retention.find_role_label_leaks([_b("point", "Clean narration.", motion_graphic=mg)]), [0])
        bare = {"sceneType": "warning", "title": "Payoff"}
        self.assertEqual(retention.find_role_label_leaks([_b("point", "Clean narration.", motion_graphic=bare)]), [0])

    def test_natural_language_uses_are_not_flagged(self):
        for text in (
            "Evidence, not hope, is what moves a budget.", "Reveal your spending to your partner.",
            "The payoff of waiting is that you keep the money.", "A setup like this takes ten minutes.",
            "Your escalation clause can raise rent.", "The resolution of the dispute took a year.",
            "Pattern recognition helps you spot impulse buys.", "The payoff, in short, is a lower bill.",
            "The real payoff of waiting is that you keep the money.", "Answer the question before you buy.",
        ):
            self.assertEqual(retention.find_role_label_leaks([_b("point", text)]), [], text)

    def test_real_fixtures_leaks_are_reported_as_high(self):
        s2 = retention.analyze(real("real_s2"))
        leak = [i for i in s2["issues"] if i["code"] == "role_label_leak"]
        self.assertEqual(len(leak), 1)
        self.assertEqual(leak[0]["severity"], "high")
        self.assertEqual(leak[0]["blocks"], [4, 6, 9, 10])  # incl. "Big escalation, ..." found once qualifiers were covered
        self.assertEqual(s2["structure"]["roleLabelLeaks"], [4, 6, 9, 10])
        self.assertEqual(retention.analyze(real("real_s3"))["structure"]["roleLabelLeaks"], [5, 9])  # "Real payoff, ..."
        self.assertEqual(retention.analyze(real("real_s4"))["structure"]["roleLabelLeaks"], [7])  # "Concrete payoff, ..."
        self.assertEqual(retention.analyze(real("real_s5"))["structure"]["roleLabelLeaks"], [])


class TestFirstPersonGuard(unittest.TestCase):
    def test_invented_experience_is_flagged(self):
        for text in (
            "I opened the metal box, counted crisp notes, and handed cash directly to the plumber.",
            "I invested five dollars every single day.", "I've saved every month since college.",
            "J'ai ouvert la boîte et j'ai compté les billets.", "When I was broke I stopped spending.",
        ):
            self.assertEqual(retention.find_first_person_anecdotes([_b("point", text)]), [0], text)

    def test_hypotheticals_and_explanations_are_not_flagged(self):
        for text in (
            "Imagine you invest five dollars a day.", "Say someone opened a metal box.", "If you save $500 first, you keep more.",
            "I'll show you how this works.", "Here is what I recommend: automate the transfer.",
            "Prenons un exemple : tu investis cinq euros par jour.",
        ):
            self.assertEqual(retention.find_first_person_anecdotes([_b("point", text)]), [], text)

    def test_severity_scales_with_evidence_and_provided_stories_are_exempt(self):
        one = retention.analyze(_script([_b("hook", "Why?"), _b("point", "I opened the box and counted notes.")]))
        flagged = [i for i in one["issues"] if i["code"] == "unsupported_first_person"]
        self.assertEqual(flagged[0]["severity"], "info")
        two = retention.analyze(_script([_b("hook", "Why?"), _b("point", "I opened the box."), _b("point", "I counted notes.")]))
        self.assertEqual([i["severity"] for i in two["issues"] if i["code"] == "unsupported_first_person"], ["high"])
        pasted = retention.analyze(_script([_b("hook", "Why?"), _b("point", "I opened the box."), _b("point", "I counted notes.")],
                                           source_type="pasted_text"))
        self.assertNotIn("unsupported_first_person", _codes(pasted))

    def test_real_fixtures(self):
        self.assertEqual(retention.analyze(real("real_s1"))["structure"]["firstPersonBlocks"], [2])
        self.assertEqual(retention.analyze(real("real_p5c"))["structure"]["firstPersonBlocks"], [0, 3])
        self.assertEqual(retention.analyze(real("real_s4"))["structure"]["firstPersonBlocks"], [])


class TestOptionalStructure(unittest.TestCase):
    def test_script_without_cta_validates_and_has_no_cta_issue(self):
        data = _script([_b("hook", "Where does your raise disappear?"), _b("point", "Mostly lifestyle inflation.", retentionRole="payoff")],
                       contentStrategy={"ctaIntent": "none"}, openLoops=[])
        script_module.validate_script(data)
        report = retention.analyze(data)
        self.assertEqual(report["cta"]["text"], "")
        self.assertEqual(_codes(report, "cta"), [])
        self.assertEqual(report["cta"]["detectedIntent"], "none")

    def test_short_structures_are_accepted(self):
        for blocks in (
            [_b("hook", "Raise gone?"), _b("point", "Lifestyle takes $850 of a $1,000 raise.")],
            [_b("hook", "Raise gone?"), _b("point", "Rent adds $400.", retentionRole="evidence"),
             _b("point", "Only $150 is left.", retentionRole="payoff")],
        ):
            data = _script(blocks)
            script_module.validate_script(data)
            self.assertEqual([i for i in retention.analyze(data)["issues"] if i["severity"] == "high"], [])

    def test_optional_loop_and_payoff_before_the_end(self):
        """La réponse peut arriver tôt : le reste de la vidéo la démontre, sans défaut."""
        blocks = [
            _b("hook", "Where does your raise disappear?", retentionRole="hook"),
            _b("point", "Mostly lifestyle inflation.", retentionRole="payoff"),
            _b("point", "Rent adds $250 and a car adds $180.", retentionRole="evidence"),
            _b("point", "Takeout adds $220 and going out $200.", retentionRole="evidence"),
            _b("point", "So only $150 of the $1,000 is left.", retentionRole="evidence"),
        ]
        report = retention.analyze(_script(blocks, contentStrategy={"coreQuestion": "Where does the raise go?"}))
        self.assertEqual(report["payoff"]["blockIndex"], 1)
        self.assertLess(report["pacing"]["payoffPositionRatio"], 0.4)
        self.assertEqual([i for i in report["issues"] if i["severity"] == "high"], [])

    def test_real_outputs_never_report_retired_codes(self):
        for name in ("real_s1", "real_s2", "real_s3", "real_s4", "real_s5", "real_p5c"):
            codes = set(_codes(retention.analyze(real(name))))
            self.assertFalse(codes & RETIRED, (name, codes & RETIRED))


class TestMetadataMismatchesAreNotDefects(unittest.TestCase):
    """The model declares ctaIntent "save" then writes a question, or declares a CTA and writes none: invisible to viewers."""

    def test_declared_vs_detected_cta_intent(self):
        blocks = [_b("hook", "Where does your raise go?"), _b("point", "Mostly lifestyle inflation."),
                  _b("cta", "Want a 30-day checklist to try this month?")]
        report = retention.analyze(_script(blocks, contentStrategy={"ctaIntent": "save"}))
        self.assertEqual(report["cta"]["declaredIntent"], "save")
        self.assertEqual(report["cta"]["detectedIntent"], "question")
        self.assertEqual(_codes(report, "cta"), [])

    def test_declared_cta_without_a_cta_block(self):
        blocks = [_b("hook", "Where does your raise go?"), _b("point", "Mostly lifestyle inflation.")]
        report = retention.analyze(_script(blocks, contentStrategy={"ctaIntent": "question"}))
        self.assertEqual(_codes(report, "cta"), [])


class TestNumberWords(unittest.TestCase):
    def test_narrow_english_normalization(self):
        cases = {
            "five dollars": "5 dollars", "ten thousand dollar balance": "10000 dollar balance",
            "twenty-six thousand dollars": "26000 dollars", "one thousand eight hundred twenty five": "1825",
            "one hundred and twenty one thousand": "121000", "five percent": "5 percent",
        }
        for src, expected in cases.items():
            self.assertEqual(retention.normalize_number_words(src), expected, src)

    def test_a_lone_one_and_plain_words_are_untouched(self):
        for text in ("Only one becomes wealthy.", "Rock and roll.", "Someone else", "tennis"):
            self.assertEqual(retention.normalize_number_words(text), text)

    def test_spelled_numbers_match_digits_in_diagnostics(self):
        hook = retention.diagnose_hook("Invest five dollars a day, watch what happens.")
        self.assertTrue(hook["containsSpecificNumber"])
        self.assertFalse(hook["delayedValue"])
        data = _script(
            [_b("hook", "Why is it hard?"), _b("point", "It takes ten thousand dollars saved.", retentionRole="payoff")],
            contentStrategy={"payoff": "You reach $10,000 over months."},
        )
        self.assertNotIn("promised_number_missing", _codes(retention.analyze(data)))

    def test_a_genuinely_missing_number_is_reported_but_only_as_information(self):
        data = _script(
            [_b("hook", "Why?"), _b("point", "It takes ten thousand dollars saved.", retentionRole="payoff")],
            contentStrategy={"payoff": "You reach $12,000 over months."},
        )
        issues = [i for i in retention.analyze(data)["issues"] if i["code"] == "promised_number_missing"]
        self.assertEqual([i["severity"] for i in issues], ["info"])  # plan/script gap: never a viewer-facing defect

    def test_rounding_and_k_notation_are_not_missing_numbers(self):
        data = _script(
            [_b("hook", "Why?"), _b("point", "That grows to about $364,000 after forty years, and $25k after ten.", retentionRole="payoff")],
            contentStrategy={"payoff": "It grows to about $364,307 in 40 years and $25,200 after 10."},
        )
        self.assertNotIn("promised_number_missing", _codes(retention.analyze(data)))

    def test_real_s4_and_s5_have_no_number_false_positives(self):
        self.assertNotIn("delayed_value", _codes(retention.analyze(real("real_s4"))))
        self.assertNotIn("promised_number_missing", _codes(retention.analyze(real("real_s5"))))


class TestConservativeDiagnostics(unittest.TestCase):
    def test_high_severity_only_for_high_confidence_codes(self):
        for name in ("real_s1", "real_s2", "real_s3", "real_s4", "real_s5", "real_p5c"):
            for issue in retention.analyze(real(name))["issues"]:
                if issue["severity"] == "high":
                    self.assertIn(issue["code"], HIGH_CONFIDENCE, (name, issue))

    def test_lexical_overlap_is_never_high(self):
        blocks = [_b("hook", "Where does the raise go?", retentionRole="hook"),
                  _b("point", "Final take, daily habits and patience pay off.", retentionRole="payoff")]
        report = retention.analyze(_script(blocks, contentStrategy={"coreQuestion": "Where does the raise go?"}))
        for issue in report["issues"]:
            if issue["code"] in ("payoff_not_resolving_hook", "resolution_not_matching"):
                self.assertEqual(issue["severity"], "info")

    def test_hook_type_is_metadata_not_a_defect(self):
        diag = retention.diagnose_hook("Wait 24 hours before you buy that thing.", "challenge")
        self.assertNotIn("hook_type_signal_missing", [i["code"] for i in diag["issues"]])
        self.assertIn("hookTypeSignal", diag)

    def test_generic_payoff_phrases(self):
        short = retention.analyze(_script([_b("hook", "Why?"), _b("point", "Consistency matters.", retentionRole="payoff")]))
        self.assertEqual([i["severity"] for i in short["issues"] if i["code"] == "generic_payoff"], ["high"])
        concrete = retention.analyze(_script([_b("hook", "Why?"), _b("point", "Consistency matters because $5 a day becomes $1,825.", retentionRole="payoff")]))
        self.assertNotIn("generic_payoff", _codes(concrete))


class TestLegacyCompatibility(unittest.TestCase):
    def test_every_existing_script_still_validates_and_analyzes(self):
        root = Path(__file__).parent.parent / "content" / "scripts"
        for path in sorted(root.glob("*.json")) + sorted((root / "benchmark").glob("*.json")):
            data = script_module.normalize_script(json.loads(path.read_text(encoding="utf-8")))
            script_module.validate_script(data)
            report = retention.analyze(data)
            self.assertEqual(report["version"], retention.VERSION)
            self.assertFalse(report["hasContentStrategy"])

    def test_diagnostics_stay_free_of_virality_claims(self):
        text = json.dumps(retention.analyze(real("real_s2")), ensure_ascii=False).lower()
        for banned in ("viral", "probab"):
            self.assertNotIn(banned, text)


class TestMotionGraphicsSemantics(unittest.TestCase):
    """The exact Phase 5.1 rendering-data failures."""

    def codes(self, scene):
        return {i["code"] for i in semantic.semantic_issues(scene)}

    def test_dollar_placeholders(self):
        scene = {"sceneType": "compound_growth", "title": "Hypothetical split example",
                 "data": [{"label": "Saved portion", "displayValue": "$Saved"}, {"label": "Spent portion", "displayValue": "$Spent"}]}
        self.assertIn("placeholder_text", self.codes(scene))
        scene = {"sceneType": "before_after", "title": "Like watering plants", "before": {"label": "No returns", "displayValue": "$1,825"},
                 "after": {"label": "With returns (example)", "displayValue": "$growth over time"}}
        self.assertIn("placeholder_text", self.codes(scene))

    def test_example_rate_and_valueless_charts(self):
        compound = {"sceneType": "compound_growth", "title": "Hypothetical annual returns",
                    "data": [{"label": "5% example", "displayValue": "example rate"}, {"label": "8% example", "displayValue": "example rate"}]}
        self.assertEqual(self.codes(compound), {"placeholder_text", "rows_without_quantity"})
        bar = {"sceneType": "bar_chart", "title": "Example growth after 10 years",
               "data": [{"label": "5% example", "displayValue": "example"}, {"label": "8% example", "displayValue": "example"}]}
        self.assertEqual(self.codes(bar), {"placeholder_text", "chart_missing_values"})

    def test_donut_legend_without_values(self):
        donut = {"sceneType": "donut_chart", "title": "Principal vs Returns (example)",
                 "data": [{"label": "Principal contributed", "displayValue": "$1,825 per year (example)"},
                          {"label": "Returns (example)", "displayValue": "Varies by rate"}]}
        self.assertIn("chart_missing_values", self.codes(donut))

    def test_empty_comparisons(self):
        yes_no = {"sceneType": "comparison", "optionA": {"label": "Yes", "displayValue": ""}, "optionB": {"label": "No", "displayValue": ""}}
        self.assertIn("empty_comparison", self.codes(yes_no))
        vs = {"sceneType": "comparison", "title": "Pick an example rate",
              "optionA": {"label": "5% example"}, "optionB": {"label": "8% example"}}
        self.assertIn("empty_comparison", self.codes(vs))
        ok = {"sceneType": "comparison", "optionA": {"label": "Impulse choice", "displayValue": "Original item"},
              "optionB": {"label": "Delayed choice", "displayValue": "Better deal found"}}
        self.assertEqual(self.codes(ok), set())

    def test_progress_bar_needs_a_real_quantity(self):
        self.assertIn("progress_without_quantity",
                      self.codes({"sceneType": "progress_bar", "displayValue": "Principal vs Total (example)", "targetRatio": 0.6}))
        self.assertEqual(self.codes({"sceneType": "progress_bar", "displayValue": "$4,200 / $10,000", "targetRatio": 0.42}), set())
        self.assertIn("bad_ratio", self.codes({"sceneType": "progress_bar", "displayValue": "$1", "targetRatio": 4}))

    def test_good_scenes_pass(self):
        good = [
            {"sceneType": "big_number", "title": "Yearly total", "displayValue": "$1,825"},
            {"sceneType": "money_split", "data": [{"label": "Spent", "value": 850, "displayValue": "$850"}, {"label": "Left", "value": 150, "displayValue": "$150"}]},
            {"sceneType": "bar_chart", "data": [{"label": "A", "value": 400}, {"label": "B", "value": 300}]},
            {"sceneType": "compound_growth", "data": [{"label": "Year 5", "displayValue": "$10,500"}, {"label": "Year 10", "displayValue": "$25,200"}]},
            {"sceneType": "before_after", "before": {"label": "Tonight", "displayValue": "I need it"}, "after": {"label": "Tomorrow", "displayValue": "Keep $45"}},
            {"sceneType": "formula", "terms": ["$1,000 RAISE", "- $850 SPENT", "= $150 LEFT"]},
            {"sceneType": "timeline", "steps": ["Want it", "Wait 24 hours", "Decide"]},
            {"sceneType": "icon_text", "text": "Wait 24 hours"},
        ]
        for scene in good:
            self.assertEqual(self.codes(scene), set(), scene)

    def test_fallback_text_never_reuses_rejected_data(self):
        scene = {"sceneType": "before_after", "title": "$growth over time",
                 "before": {"label": "No returns", "displayValue": "$1,825"}, "after": {"label": "x", "displayValue": "$growth over time"}}
        out = semantic.fallback_scene(scene, "Fast forward ten years using examples. Different rates give different totals.")
        self.assertNotIn("$growth", json.dumps(out))
        self.assertEqual(out, {"sceneType": "big_number", "displayValue": "$1,825", "title": "No returns"})  # the one readable fact
        out = semantic.fallback_scene({"sceneType": "bar_chart", "title": "$growth"}, "Fast forward ten years using examples. Different rates differ.")
        self.assertEqual(out, {"sceneType": "icon_text", "text": "Fast forward ten years using examples"})
        self.assertEqual(semantic.fallback_text({"title": "Example growth after 10 years"}, "ignored"), "Example growth after 10 years")

    def test_fallback_selection_uses_existing_scene_types(self):
        pick = lambda scene: semantic.fallback_scene(scene, "Practically it covers small crises, for example a $400 car repair or a $300 urgent vet bill.")
        # invalid comparison with one readable number -> big_number; with nothing readable -> short typography
        self.assertEqual(pick({"sceneType": "comparison", "optionA": {"label": "With buffer", "displayValue": "$1,000"}, "optionB": {"label": "Without"}})["sceneType"], "big_number")
        self.assertEqual(pick({"sceneType": "comparison", "optionA": {"label": "Yes"}, "optionB": {"label": "No"}})["sceneType"], "icon_text")
        # chart with a single usable number -> big_number ; several usable facts but no numeric series -> checklist
        one = pick({"sceneType": "bar_chart", "data": [{"label": "A", "displayValue": "$400"}, {"label": "B", "displayValue": "example"}]})
        self.assertEqual((one["sceneType"], one["displayValue"]), ("big_number", "$400"))
        many = pick({"sceneType": "money_split", "data": [{"label": "Rent", "displayValue": "$400"}, {"label": "Car", "displayValue": "$300"}]})
        self.assertEqual(many["sceneType"], "checklist")
        self.assertEqual(many["items"], ["Rent: $400", "Car: $300"])
        # progress bar with a visible amount -> big_number (the ratio is never shown)
        bar = pick({"sceneType": "progress_bar", "displayValue": "25 months", "targetRatio": 4})
        self.assertEqual(bar, {"sceneType": "big_number", "displayValue": "25 months"})
        # last resort only: generic typography
        self.assertEqual(pick({"sceneType": "bar_chart", "data": []})["sceneType"], "icon_text")
        # every fallback scene is itself structurally valid for the renderer
        from engine.motion_graphics import schema
        for scene in (bar, many, one):
            self.assertIsNotNone(schema.validate_scene(scene))

    def test_fallback_display_text_is_an_intentional_short_phrase(self):
        long_sentences = [
            "Once you have $1,000, keep growing it toward three to six months of expenses as your next goal.",
            "That $1,000 typically covers one medium shock, like a $400 car repair and a $600 ER bill.",
            "Practically it covers small crises, for example a $400 car repair or a $300 urgent vet bill, hypothetical examples.",
            "Think of $1,000 like a spare tire, it gets you home without calling a tow.",
        ]
        for sentence in long_sentences:
            text = semantic.display_phrase(sentence)
            self.assertTrue(text, sentence)
            self.assertNotIn("…", text)
            self.assertNotIn("...", text)
            self.assertLessEqual(len(text.split()), 9)
            self.assertIn(text.rstrip(".,"), sentence)  # a contiguous, whole clause of the narration, never a cut word
        self.assertEqual(semantic.display_phrase("Once you have $1,000, keep growing it toward three to six months of expenses."), "Once you have $1,000")
        self.assertEqual(semantic.display_phrase("word " * 40), "")  # no whole clause fits: the caller picks another source
        from engine.motion_graphics import preflight
        text = preflight.fallback_text(None, "That $1,000 typically covers one medium shock, like a $400 car repair and a $600 ER bill.")
        self.assertEqual(text, "That $1,000 typically covers one medium shock")
        self.assertNotIn("…", preflight.fallback_text(None, "word " * 100))

    def test_real_phase_51_scripts_are_screened(self):
        s4 = real("real_s4")
        flagged = {i for i, b in enumerate(s4["blocks"]) if semantic.semantic_issues(b["motion_graphic"])}
        self.assertTrue({3, 5, 6, 7, 11} <= flagged)

    def test_fallback_is_recorded_by_the_pipeline_entry(self):
        from engine import visuals

        scene = {"sceneType": "icon_text", "text": "Fast forward ten years"}
        report: list = []
        visuals._sync_and_preflight(scene, "Fast forward", 3.0, Path("missing.words.json"), (1080, 1920), None, 6, report,
                                    [{"code": "chart_missing_values", "message": "x"}])
        self.assertEqual(report[0]["action"], "fallback_semantic")
        self.assertEqual(report[0]["semanticIssues"], ["chart_missing_values"])
        report2: list = []
        visuals._sync_and_preflight(scene, "Fast forward", 3.0, Path("missing.words.json"), (1080, 1920), None, 2, report2, None, True)
        self.assertEqual(report2[0]["action"], "fallback_schema")


class TestNoDerivedFinancialValues(unittest.TestCase):
    """Phase 5.1 showed "49%" and "58%" on progress bars: `targetRatio` (a fill-level parameter) was drawn as a percentage."""

    def drawn_texts(self, scene, t):
        theme = resolve_theme(None)
        with layout.record_boxes() as recorded:
            scenes.render_progress_bar(scene, t, theme, (1080, 1920))
        return [r["text"] for r in recorded]

    def test_target_ratio_is_never_rendered_as_text(self):
        for ratio in (0.5, 0.6, 0.97):
            scene = {"sceneType": "progress_bar", "title": "Saving $400 a month", "displayValue": "25 months", "targetRatio": ratio}
            for t in (0.2, 0.6, 1.0):
                texts = self.drawn_texts(scene, t)
                self.assertFalse([x for x in texts if "%" in x], (ratio, t, texts))
                self.assertIn("25 months", " ".join(texts))

    def test_a_percentage_the_script_supplies_is_still_shown(self):
        scene = {"sceneType": "progress_bar", "displayValue": "42% saved", "targetRatio": 0.42}
        self.assertIn("42% saved", " ".join(self.drawn_texts(scene, 1.0)))


if __name__ == "__main__":
    unittest.main()
