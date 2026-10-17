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


class TestDirectorNeverBlocks(unittest.TestCase):
    def test_unresolvable_anchor_after_repairs_is_reported_not_fatal(self):
        from engine.explainer import director
        sb = storyboard()
        sb["plans"][0]["anchors"] = [{"id": "send", "text": "mot inexistant"}]
        narration, words = timeline.estimate_narration(LINES)
        total = timeline.total_duration(narration, words)
        calls = []

        def complete(spend, step, model, system, user, **kw):
            calls.append(step)
            return "```json\n" + json.dumps(sb) + "\n```"
        with mock.patch.object(llm, "complete", complete):
            result = director.direct(llm.Spend(), "test", narration, words, total)
        self.assertEqual(len(calls), director.MAX_REPAIRS + 1)
        self.assertTrue(result["anchorWarnings"])


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

    def test_box_is_upright_by_default_and_corner_is_not_rotation(self):
        # regression : `r` etait a la fois rotation et rayon des coins, toute box sans r etait tournee de 16 rad
        if not HAVE_PLAYWRIGHT:
            self.skipTest("playwright non installé")
        import asyncio
        import io
        from PIL import Image
        from engine.explainer import render
        code = "S.sky('void');S.add('box',{x:540,y:960,w:800,h:120,color:'#ff0000',corner:20});"
        with tempfile.TemporaryDirectory() as tmp:
            timeline_path = Path(tmp) / "t.js"
            timeline_path.write_text(validate.plan_module(code, "x", 3.0, {}), encoding="utf-8")
            png = asyncio.run(render.render_stills_async(timeline_path, [1.0], Path(tmp) / "out"))[0].read_bytes()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        for x in (180, 540, 900):
            self.assertEqual(img.getpixel((x, 960))[0] > 200 and img.getpixel((x, 960))[1] < 60, True, f"box absente ou tournée en x={x}")
        self.assertFalse(img.getpixel((540, 760))[0] > 200 and img.getpixel((540, 760))[1] < 60)

    def test_nearly_empty_frame_is_rejected(self):
        if not HAVE_PLAYWRIGHT:
            self.skipTest("playwright non installé")
        result = validate.validate_plan("S.sky('void');const t=S.add('text',{text:'OK',x:540,y:900,size:64});", "x", 4.0, {})
        self.assertTrue(any("premier plan vide" in e for e in result["errors"]), result["errors"])
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
        simple = "S.sky('night');S.template('title',{text:'OCEAN',sub:'ondes'});S.cam.to(0,S.dur,{x:540,y:960,z:1.1});"
        def complete2(spend, step, model, system, user, **kw):
            if step.startswith("animator:p1"):
                return "```js\n" + reference + "\n```"
            if step.startswith("animator:p2"):
                return "```js\n" + simple + "\n```"
            return complete(spend, step, model, system, user, **kw)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(llm, "complete", complete2):
            report = pipeline.generate("test", tmp, lines=LINES, do_render=False, use_critic=False, log=lambda *_: None)
            self.assertEqual(report["fallbacks"], [])
            self.assertTrue(report["timingsAreEstimated"])
            self.assertEqual([p["ok"] for p in report["plans"]], [True, True])
            js = Path(tmp, "explainer.timeline.js").read_text(encoding="utf-8")
            self.assertIn("Faceloop.define", js)
            self.assertTrue(Path(tmp, "explainer.report.json").exists())

    def test_failing_plan_falls_back_to_pillow_and_is_reported(self):
        simple = "S.sky('night');S.template('title',{text:'OCEAN',sub:'ondes'});S.cam.to(0,S.dur,{x:540,y:960,z:1.1});"
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
            report = pipeline.generate("test", tmp, lines=LINES, do_render=True, use_critic=False, log=lambda *_: None)
            self.assertEqual([f["plan"] for f in report["fallbacks"]], ["p2"])
            self.assertEqual(len([c for c in calls if c.startswith("animator:p2")]), animator.MAX_REPAIRS + 1)
            self.assertTrue(Path(report["video"]).exists())
            self.assertGreater(Path(report["video"]).stat().st_size, 10000)


def director_module():
    from engine.explainer import director
    return director


def critic_json(avg, issues=True):
    scores = {k: avg for k in ("hook", "continuite", "lisibilite", "clarte", "rythme", "finition", "justesse")}
    scores.update({"synchro": None, "son": None})
    body = {"scores": scores, "issues": [{"critere": "finition", "image": 2, "probleme": "vide", "correction": "agrandir le titre"}] if issues else [], "faits": []}
    return "```json\n" + json.dumps(body) + "\n```"


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright non installé")
class TestCriticLoop(unittest.TestCase):
    PLAN = "S.sky('night');S.template('title',{text:'OCEAN',sub:'ondes'});S.cam.to(0,S.dur,{x:540,y:960,z:1.1});"
    BETTER = PLAN + "const u=S.add('text',{text:'ONDES',x:540,y:1450,size:80,color:'accent'});u.appear(0.8,0.4,'up');"

    def run_pipeline(self, critic_scores):
        calls = []
        sb = storyboard()
        sb["plans"][0]["anchors"] = []
        scores = iter(critic_scores)

        def complete(spend, step, model, system, user, **kw):
            calls.append(step)
            if step == "factcheck":
                return "```json\n" + json.dumps({"verdict": "a_reviser", "flags": [{"ligne": 1, "type": "trompeur", "pourquoi": "test", "reformulation": "Elle appuie sur le bouton."}]}) + "\n```"
            if step.startswith("critic:"):
                return critic_json(next(scores))
            if step.startswith("improve:"):
                return "```js\n" + self.BETTER + "\n```"
            return "```js\n" + self.PLAN + "\n```"

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(llm, "complete", complete), \
                mock.patch.object(director_module(), "direct", lambda spend, *a, **k: {"storyboard": sb, "attempts": 1}):
            report = pipeline.generate("test", tmp, lines=list(LINES), do_render=False, log=lambda *_: None)
            return report, calls, Path(tmp, "plans", "p1.js").read_text(encoding="utf-8")

    def test_weak_plan_is_improved_and_better_version_is_kept(self):
        report, calls, final = self.run_pipeline([3.0, 3.0, 4.5, 4.5])   # v0: p1=3, p2=3 ; v1 : p1=4,5 p2=4,5
        self.assertTrue(any(c.startswith("improve:") for c in calls))
        self.assertEqual(report["lineEdits"][0]["after"], "Elle appuie sur le bouton.")
        self.assertIn("ONDES", final)
        self.assertEqual(report["critic"]["plans"]["p1"]["history"][-1]["kept"], "new")
        self.assertGreaterEqual(report["critic"]["videoAverage"], 4.0)
        self.assertTrue(report["critic"]["syncAndSoundNotEvaluated"])

    def test_regression_is_rejected_and_previous_version_kept(self):
        report, calls, final = self.run_pipeline([3.5, 3.5, 2.0, 2.0, 2.0, 2.0])
        self.assertNotIn("ONDES", final)
        self.assertEqual(report["critic"]["plans"]["p1"]["history"][1]["kept"], "previous")

    def test_good_plans_are_left_alone(self):
        report, calls, final = self.run_pipeline([4.5, 4.5])
        self.assertFalse(any(c.startswith("improve:") for c in calls))
        self.assertNotIn("ONDES", final)


TEMPLATE_CASES = {
    "title": "S.sky('night');S.template('title',{text:'Le nombre d or',sub:'une proportion partout'});S.cam.to(0,S.dur,{x:540,y:960,z:1.08});",
    "equation": "S.grid(true);S.template('equation',{lines:[{text:'2x + 3 = 11',t:0},{text:'2x = 11 - 3',t:1.5,note:'- 3 des deux cotes'},{text:'2x = 8',t:3},{text:'x = 4',t:4.5}]});",
    "bignumber": "S.grid(true);S.template('bignumber',{from:1000,to:2594,t0:1,t1:4,suffix:' EUR',label:'apres 10 ans',labelT:4});",
    "bars": "S.grid(true);S.template('bars',{title:'Le capital grandit',values:[1,1.1,1.21,1.33,1.46,1.61,1.77,1.95,2.14,2.36,2.59],t0:0.4,t1:4,readout:'x 2,59',readoutT:4});",
    "linechart": "S.grid(true);S.template('linechart',{title:'Convergence',values:[1,2,1.5,1.667,1.6,1.625,1.615,1.619,1.618],t0:0.4,t1:4,ref:{value:1.618,label:'phi'},xlabel:'rang'});",
    "bullets": "S.grid(true);S.template('bullets',{title:'Trois etapes',items:[{text:'Chiffrer',t:0.8},{text:'Decouper',t:2.2},{text:'Router',t:3.6}]});",
    "compare": "S.grid(true);S.template('compare',{left:{title:'Reel',items:['Petales','Coquillages']},right:{title:'Mythe',items:['Pyramides','Mona Lisa']}});",
    "flow": "S.grid(true);S.template('flow',{nodes:[{label:'Telephone',t:0.4},{label:'Antenne',t:1.4},{label:'Cable',t:2.4},{label:'Data center',t:3.4},{label:'Ton ami',t:4.4}]});",
    "segment": "S.grid(true);S.template('segment',{tCut:1.5});S.cam.to(0,S.dur,{x:540,y:960,z:1.1});",
    "fibonacci": "S.grid(true);S.template('fibonacci',{t0:0.2,t1:5,n:8});S.cam.to(0,S.dur,{x:540,y:960,z:1.1});",
    "room-send": "S.template('room',{place:'dakar',who:'awa',tag:'DAKAR',contact:'Lea',message:'On mange ce soir ?',sendAt:4,zoomPhone:{t0:5.2,t1:6.8}});",
    "room-receive": "S.template('room',{place:'paris',who:'lea',tag:'PARIS',contact:'Awa',message:'On mange ce soir ?',receiveAt:1,reply:'Oui, 20h !',replyFrom:4.2,replyAt:6.4,smileAt:5});",
    "journey": "S.template('journey',{});",
    "equation-guide": "S.grid(true);S.template('equation',{lines:[{text:'2x + 3 = 11',t:0},{text:'2x = 8',t:2.5},{text:'x = 4',t:4.5}]});S.template('guide',{who:'awa',side:'left',size:0.8,poses:[{t:0,pose:'wave'},{t:2.5,pose:'point'},{t:4.5,pose:'cheer'}],say:[{t:0.3,text:'Salut !',until:1.6}]});",
    "guide-title": "S.sky('night');S.template('title',{text:'Bravo !',sub:'tu as compris'});S.template('guide',{who:'sam',side:'left',size:1.0,y:1650,poses:[{t:0,pose:'cheer'}]});S.template('guide',{who:'malik',side:'right',size:1.0,y:1650,poses:[{t:0,pose:'wave'}]});",
}


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright non installé")
class TestTemplates(unittest.TestCase):
    def test_every_template_passes_the_validator(self):
        for name, code in TEMPLATE_CASES.items():
            dur = 22.0 if name == "journey" else 8.0 if name.startswith(("room", "equation-guide")) else 7.0
            result = validate.validate_plan(code, "t_" + name.replace("-", "_"), dur, {}, name.split("-")[0] if name.split("-")[0] in ("room", "journey") else "equation" if name == "equation-guide" else "scene")
            self.assertTrue(result["ok"], (name, result["errors"]))

    def test_unknown_template_and_missing_param_fail_the_plan(self):
        for code, expected in (("S.template('nimportequoi',{});", "gabarit inconnu"), ("S.template('bignumber',{});", "manquant")):
            result = validate.validate_plan("S.grid(true);" + code, "x", 5.0, {})
            self.assertFalse(result["ok"])
            self.assertTrue(any(expected in e for e in result["errors"]), result["errors"])

    def test_reference_plans_all_validate(self):
        for name, spec in animator.REFERENCES.items():
            code = Path(animator.PLANS_DIR, name + ".plan.js").read_text(encoding="utf-8")
            result = validate.validate_plan(code, name.replace("-", "_"), spec["duration"], spec["anchors"])
            self.assertTrue(result["ok"], (name, result["errors"]))


class TestLayout(unittest.TestCase):
    def test_schema_accepts_scene_and_template_layouts_and_rejects_unknown(self):
        sb = storyboard()
        sb["plans"][0]["layout"] = "equation"
        self.assertEqual(schema.validate_storyboard(sb, 4), [])
        sb["plans"][0]["layout"] = "diaporama"
        self.assertTrue(any("layout" in p for p in schema.validate_storyboard(sb, 4)))

    def test_required_template_must_be_called(self):
        code = "S.grid(true);S.template('equation',{lines:[{text:'x = 1',t:0}]});"
        self.assertEqual(validate.static_check(code, ("equation",)), [])
        self.assertTrue(any("layout" in e for e in validate.static_check("S.grid(true);", ("equation",))))
        self.assertTrue(any("layout" in e for e in validate.static_check(code, ("bars",))))
        self.assertEqual(validate.static_check("S.grid(true);", ()), [])

    def test_brief_carries_the_layout_and_references_declare_theirs(self):
        sb = storyboard()
        sb["plans"][0]["layout"] = "flow"
        brief = json.loads(animator.plan_brief(sb["plans"][0], 5.0, {}, "texte", "sujet", {}, {}))
        self.assertEqual(brief["layout"], "flow")
        self.assertEqual(animator.REFERENCES["equation-steps"]["layout"], "equation")
        for name, spec in animator.REFERENCES.items():
            code = Path(animator.PLANS_DIR, name + ".plan.js").read_text(encoding="utf-8")
            self.assertEqual(validate.static_check(code, () if spec.get("layout", "scene") == "scene" else (spec["layout"],)), [], name)


class TestLayoutProbe(unittest.TestCase):
    """Règles de mise en page sur les boîtes des formes (éléments coupés par un bord, texte recouvert)."""

    @staticmethod
    def shape(kind, order, seq, x0, x1, y0, y1, op="fill", alpha=1.0):
        return {"kind": kind, "order": order, "seq": seq, "op": op, "alpha": alpha, "x0": x0, "x1": x1, "y0": y0, "y1": y1}

    def report(self, shapes, texts=(), t=1.0):
        return {"t": t, "shapes": list(shapes), "texts": list(texts), "ms": 1, "errors": []}

    def test_box_cut_by_one_edge_is_flagged_but_not_scenery_or_two_edges(self):
        cut = self.shape("box", 1, 0, 700, 1180, 400, 520)                       # dépasse le bord droit (1080) de 100 px sur 480
        self.assertEqual([f["rule"] for f in validate.layout_findings(self.report([cut]))], ["cut"])
        scenery = self.shape("water", 2, 1, 700, 1180, 400, 520)
        self.assertEqual(validate.layout_findings(self.report([scenery])), [])
        both = self.shape("box", 3, 2, -200, 1300, 400, 520)                      # traverse tout l'écran : décor, pas objet coupé
        self.assertEqual(validate.layout_findings(self.report([both])), [])
        inside = self.shape("box", 4, 3, 100, 600, 400, 520)
        self.assertEqual(validate.layout_findings(self.report([inside])), [])

    def test_mostly_offscreen_element_is_an_entrance_not_a_defect(self):
        sliding = self.shape("box", 1, 0, 1000, 1500, 400, 520)                   # presque entièrement hors cadre
        self.assertEqual(validate.layout_findings(self.report([sliding])), [])

    def test_text_covered_by_later_shape_is_flagged_but_not_text_over_shape(self):
        text = {"s": "Année 1", "seq": 5, "order": 9, "alpha": 1.0, "x0": 100, "x1": 400, "y0": 800, "y1": 880}
        over = self.shape("circle", 2, 6, 150, 350, 780, 900)
        self.assertEqual([f["rule"] for f in validate.layout_findings(self.report([over], [text]))], ["cover"])
        under = self.shape("circle", 2, 4, 150, 350, 780, 900)                    # dessiné AVANT le texte : le texte reste lisible
        self.assertEqual(validate.layout_findings(self.report([under], [text])), [])
        halo = self.shape("circle", 2, 6, 150, 350, 780, 900, alpha=0.1)
        self.assertEqual(validate.layout_findings(self.report([halo], [text])), [])
        backdrop = self.shape("circle", 2, 6, -400, 1500, 300, 1700)              # fond immense : pas un objet
        self.assertEqual(validate.layout_findings(self.report([backdrop], [text])), [])

    def test_a_finding_needs_two_frames(self):
        f = {"rule": "cut", "key": "box#1", "msg": "coupé", "t": 1.0}
        self.assertEqual(validate.aggregate_findings([[f], []]), [])
        errors = validate.aggregate_findings([[f], [{**f, "t": 2.0}]])
        self.assertEqual(len(errors), 1)
        self.assertIn("1.0s", errors[0])

    @unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright non installé")
    def test_box_cut_by_the_edge_is_rejected_in_chromium(self):
        code = ("S.sky('void');S.grid(true);S.add('text',{text:'Titre',x:540,y:300,size:90});"
                "S.add('box',{x:900,y:960,w:520,h:200,color:'cyan'});S.add('box',{x:300,y:1400,w:400,h:200,color:'amber'});")
        result = validate.validate_plan(code, "x", 4.0, {})
        self.assertTrue(any("coupé par le bord droit" in e for e in result["errors"]), result["errors"])
        ok = validate.validate_plan(code.replace("x:900", "x:600"), "x", 4.0, {})
        self.assertFalse(any("coupé par le bord" in e for e in ok["errors"]), ok["errors"])


class TestTransientErrors(unittest.TestCase):
    def test_network_cut_mid_stream_is_retried_then_reported_not_fatal(self):
        class Boom(Exception):
            pass
        Boom.__module__ = "httpx2._exceptions"
        calls = []

        class Client:
            class messages:
                @staticmethod
                def stream(**kw):
                    calls.append(1)
                    raise Boom("peer closed connection")

        with mock.patch.object(llm, "client", lambda: Client()), mock.patch.object(llm.time, "sleep", lambda s: None):
            with self.assertRaises(RuntimeError) as ctx:
                llm.complete(llm.Spend(), "x", "claude-sonnet-5-5", "sys", "user")
        self.assertEqual(len(calls), llm.STREAM_ATTEMPTS)
        self.assertIn("réseau Claude indisponible", str(ctx.exception))

    def test_non_transient_error_is_not_retried(self):
        calls = []

        class Client:
            class messages:
                @staticmethod
                def stream(**kw):
                    calls.append(1)
                    raise ValueError("requête invalide")

        with mock.patch.object(llm, "client", lambda: Client()):
            with self.assertRaises(ValueError):
                llm.complete(llm.Spend(), "x", "claude-sonnet-5-5", "sys", "user")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
