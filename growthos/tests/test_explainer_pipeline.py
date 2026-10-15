"""Phase 3 de l'Explainer : schéma, timeline, validation statique, budget, et pipeline de bout en bout avec un LLM simulé
(aucun appel réseau, aucun coût). Le rendu Chromium est ignoré si Playwright/Chromium sont absents."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.explainer import animator, llm, pipeline, schema, timeline, validate  # noqa: E402

try:
    import playwright  # noqa: F401
    HAVE_PLAYWRIGHT = True
except ImportError:  # pragma: no cover
    HAVE_PLAYWRIGHT = False

LINES = ["Awa écrit un message à son amie.", "Elle appuie sur Envoyer.", "Le message traverse l'océan.", "Léa le reçoit."]


def storyboard(first_code_anchor="send"):
    return {
        "version": schema.STORYBOARD_VERSION, "truthMode": "fact",
        "world": {"metaphor": "un message qui voyage"}, "bible": {"characters": []},
        "plans": [
            {"id": "p1", "lines": [0, 1], "intent": "envoyer", "visual": "un téléphone", "camera": "zoom",
             "anchors": [{"id": first_code_anchor, "text": "Envoyer"}], "transitionOut": "dip", "claims": [{"text": "un message est envoyé", "kind": "mechanism", "source": None}]},
            {"id": "p2", "lines": [2, 3], "intent": "traverser", "visual": "l'océan", "camera": "pan", "anchors": [], "transitionOut": "cut"},
        ],
    }


class TestSchema(unittest.TestCase):
    def test_valid_storyboard_has_no_problem(self):
        self.assertEqual(schema.validate_storyboard(storyboard(), 4), [])

    def test_gap_in_lines_and_wrong_total_are_reported(self):
        sb = storyboard()
        sb["plans"][1]["lines"] = [3]
        problems = schema.validate_storyboard(sb, 4)
        self.assertTrue(any("contigu" in p for p in problems))

    def test_unsourced_figure_is_rejected(self):
        sb = storyboard()
        sb["plans"][0]["claims"] = [{"text": "80 % du trafic", "kind": "figure", "source": None}]
        self.assertTrue(any("sans source" in p for p in schema.validate_storyboard(sb, 4)))

    def test_not_a_dict_and_bad_id(self):
        self.assertTrue(schema.validate_storyboard([], 4))
        sb = storyboard()
        sb["plans"][0]["id"] = "P 1"
        self.assertTrue(any("id invalide" in p for p in schema.validate_storyboard(sb, 4)))


class TestTimeline(unittest.TestCase):
    def test_estimates_are_ordered_and_marked_by_the_pipeline(self):
        narration, words = timeline.estimate_narration(LINES)
        self.assertEqual([n[1] for n in narration], LINES)
        self.assertEqual(sorted(w["start"] for w in words), [w["start"] for w in words])
        self.assertEqual({w["line"] for w in words}, {0, 1, 2, 3})

    def test_anchor_resolution_accent_and_multiword(self):
        narration, words = timeline.estimate_narration(LINES)
        total = timeline.total_duration(narration, words)
        sb = storyboard()
        win = timeline.plan_windows(sb, narration, total)
        times, missing = timeline.resolve_anchors(sb["plans"][0], win[0], words)
        self.assertEqual(missing, [])
        self.assertGreater(times["send"], 0)
        sb["plans"][0]["anchors"] = [{"id": "x", "text": "appuie sur envoyer"}, {"id": "y", "text": "introuvable"}]
        times, missing = timeline.resolve_anchors(sb["plans"][0], win[0], words)
        self.assertEqual(len(missing), 1)
        self.assertIn("y", times)  # une ancre introuvable tombe sur le début du plan, et est signalée

    def test_windows_tile_the_whole_video(self):
        narration, words = timeline.estimate_narration(LINES)
        total = timeline.total_duration(narration, words)
        win = timeline.plan_windows(storyboard(), narration, total)
        self.assertEqual(win[0]["start"], 0.0)
        self.assertAlmostEqual(win[0]["start"] + win[0]["duration"], win[1]["start"], places=2)
        self.assertAlmostEqual(win[1]["start"] + win[1]["duration"], total, places=1)


class TestStaticCheck(unittest.TestCase):
    def test_references_pass(self):
        for path in (Path(animator.PLANS_DIR)).glob("*.plan.js"):
            self.assertEqual(validate.static_check(path.read_text(encoding="utf-8")), [], path.name)

    def test_hostile_code_is_rejected(self):
        for code in ("fetch('https://x')", "window.x=1", "const a=new Date()", "S.constructor", "while(true){}", "for(;;){}",
                     "const a=Math.random()", "const a = b ?? c", "eval('1')", "document.title='x'", "import('x')", "S.x.__proto__.y=1"):
            self.assertTrue(validate.static_check(code), code)

    def test_constructed_string_access_is_stopped_at_runtime(self):
        # l'analyse statique ne voit pas S[k] ; c'est le Function.prototype.constructor neutralise dans la page qui l'arrete
        if not HAVE_PLAYWRIGHT:
            self.skipTest("playwright non installé")
        result = validate.validate_plan("const k='con'+'structor'; S[k][k]('return 1')()", "x", 3.0, {})
        self.assertFalse(result["ok"])
        self.assertTrue(any("interdit" in e or "essai Chromium" in e for e in result["errors"]), result)

    def test_strict_types_colors_and_unknown_props_fail_the_plan(self):
        if not HAVE_PLAYWRIGHT:
            self.skipTest("playwright non installé")
        cases = {"dark": ("S.add('house',{dark:true})", "doit être un nombre"), "color": ("S.add('box',{color:'red'})", "couleur invalide"),
                 "prop": ("S.add('box',{colour:'ink'})", "propriété inconnue"), "pid": ("S.add('person',{pid:'awa'})", "doit être un nombre")}
        for name, (code, expected) in cases.items():
            result = validate.validate_plan(code + ";S.sky('night')", "x", 4.0, {})
            self.assertFalse(result["ok"], name)
            self.assertTrue(any(expected in e for e in result["errors"]), (name, result["errors"]))

    def test_nearly_empty_frame_is_rejected(self):
        if not HAVE_PLAYWRIGHT:
            self.skipTest("playwright non installé")
        result = validate.validate_plan("S.sky('void');const t=S.add('text',{text:'OK',x:540,y:900,size:64});", "x", 4.0, {})
        self.assertFalse(result["ok"])
        self.assertTrue(any("cadre presque vide" in e for e in result["errors"]), result["errors"])

    def test_too_long_code(self):
        self.assertTrue(validate.static_check("const a=1;\n" * 5000))


class TestSpend(unittest.TestCase):
    def test_cost_from_usage_and_unknown_model(self):
        spend = llm.Spend(limit_usd=1.0)
        usage = types.SimpleNamespace(input_tokens=1000, output_tokens=1000, cache_read_input_tokens=10000, cache_creation_input_tokens=0)
        entry = spend.record("x", "claude-sonnet-5-5", usage)
        self.assertAlmostEqual(entry["costUsd"], (1000 * 2 + 1000 * 10 + 10000 * 0.2) / 1e6, places=6)
        self.assertIsNone(spend.record("y", "modele-inconnu", usage)["costUsd"])
        self.assertTrue(spend.has_unknown_cost)

    def test_budget_blocks_further_calls(self):
        spend = llm.Spend(limit_usd=0.001)
        spend.record("x", "claude-opus-5-5", types.SimpleNamespace(input_tokens=10000, output_tokens=1000))
        with self.assertRaises(llm.BudgetExceeded):
            spend.check()

    def test_json_and_code_extraction(self):
        self.assertEqual(llm.extract_json("blabla ```json\n{\"a\": 1}\n``` fin"), {"a": 1})
        self.assertEqual(llm.extract_json("{\"a\": 2}"), {"a": 2})
        self.assertEqual(llm.extract_code("x ```js\nconst a=1;\n``` y"), "const a=1;")


def fake_complete(good_code, bad_plan_id=None):
    reference = Path(animator.PLANS_DIR, "chat-send.plan.js").read_text(encoding="utf-8")

    def complete(spend, step, model, system, user, max_tokens=16000, effort="medium"):
        if step.startswith("director"):
            return "```json\n" + json.dumps(storyboard()) + "\n```"
        plan_id = step.split(":")[1].split("#")[0]
        code = "fetch('https://exemple.test')" if plan_id == bad_plan_id else good_code
        return "```js\n" + code + "\n```"
    return complete, reference


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright non installé")
class TestPipelineWithFakeLlm(unittest.TestCase):
    def test_end_to_end_without_fallback(self):
        complete, reference = fake_complete(Path(animator.PLANS_DIR, "chat-send.plan.js").read_text(encoding="utf-8").replace("S.t('send')", "S.t('send')"))
        # le plan p2 n'a pas d'ancre : le code de référence en demande une, on utilise un plan sans ancre
        simple = "S.sky('night');const t=S.add('text',{text:'OCEAN',x:540,y:900,size:96,color:'primary'});t.appear(0.3,0.5,'up');S.cam.to(0,S.dur,{x:540,y:960,z:1.1});"
        def complete2(spend, step, model, system, user, **kw):
            if step.startswith("animator:p1"):
                return "```js\n" + reference + "\n```"
            if step.startswith("animator:p2"):
                return "```js\n" + simple + "\n```"
            return complete(spend, step, model, system, user, **kw)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(llm, "complete", complete2):
            report = pipeline.generate("test", tmp, lines=LINES, do_render=False, log=lambda *_: None)
            self.assertEqual(report["fallbacks"], [])
            self.assertTrue(report["timingsAreEstimated"])
            self.assertEqual([p["ok"] for p in report["plans"]], [True, True])
            js = Path(tmp, "explainer.timeline.js").read_text(encoding="utf-8")
            self.assertIn("Faceloop.define", js)
            self.assertTrue(Path(tmp, "explainer.report.json").exists())

    def test_failing_plan_falls_back_to_pillow_and_is_reported(self):
        simple = "S.sky('night');const t=S.add('text',{text:'OCEAN',x:540,y:900,size:96,color:'primary'});t.appear(0.3,0.5,'up');"
        calls = []

        def complete(spend, step, model, system, user, **kw):
            calls.append(step)
            if step.startswith("director"):
                return "```json\n" + json.dumps(storyboard()) + "\n```"
            return "```js\n" + ("fetch('https://x')" if ":p2" in step else simple.replace("S.t('send')", "0")) + "\n```"

        sb = storyboard()
        sb["plans"][0]["anchors"] = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(llm, "complete", complete), \
                mock.patch.object(director_module(), "direct", lambda spend, *a, **k: {"storyboard": sb, "attempts": 1}):
            report = pipeline.generate("test", tmp, lines=LINES, do_render=True, log=lambda *_: None)
            self.assertEqual([f["plan"] for f in report["fallbacks"]], ["p2"])
            self.assertEqual(len([c for c in calls if c.startswith("animator:p2")]), animator.MAX_REPAIRS + 1)
            self.assertTrue(Path(report["video"]).exists())
            self.assertGreater(Path(report["video"]).stat().st_size, 10000)


def director_module():
    from engine.explainer import director
    return director


if __name__ == "__main__":
    unittest.main()
