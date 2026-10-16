"""Validation d'un plan écrit par l'animateur : analyse statique (liste blanche) puis essai dans Chromium.

Un plan ne passe à la suite que si tout est vert (voir docs/explainer-plan.md §3.2.5) :
1. analyse statique : seulement la syntaxe et les identifiants de la liste blanche ; pas de `fetch`, `eval`,
   `import`, `new`, `this`, `while`, accès DOM, `Date`, `Math.random`, ni d'accès dynamique à `constructor` ;
2. exécution d'essai dans Chromium, réseau coupé, avec un garde-fou de durée ;
3. aucune erreur JS, aucune erreur de construction du plan (ancre inconnue, élément inconnu) ;
4. budget de temps par image ;
5. sondes : texte coupé par le bord de l'écran, texte qui en recouvre un autre, texte dans une zone de sécurité ;
6. déterminisme : deux rendus du même `t` donnent la même image.

Le code ne s'exécute JAMAIS en Python ni en Node : seulement dans la page Chromium isolée de render.py.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import esprima

from . import render

MAX_CODE_CHARS = 14000
FRAME_BUDGET_MS = 250
TRIAL_TIMEOUT_S = 45
MIN_COVERAGE = 0.008   # part minimale de cellules contrastees (contraste local, pas la couleur dominante)
FIRST_FRAME_MIN = 0.003  # un seul titre suffit à ne pas être « vide » ; un fond uni seul, si
BAND_MIN = 0.01        # part minimale de cellules contrastees pour qu'une bande horizontale compte comme occupee
ALLOWED_GLOBALS = {"S", "Math", "hash", "W", "H", "Number", "String", "Array", "undefined", "Infinity", "NaN"}
ALLOWED_MATH = {"abs", "sin", "cos", "tan", "atan", "atan2", "PI", "pow", "min", "max", "floor", "ceil", "round", "sqrt", "exp", "log", "sign", "hypot", "trunc"}
FORBIDDEN_PROPS = {"constructor", "__proto__", "prototype", "call", "apply", "bind", "eval", "Function", "caller", "callee",
                   "__defineGetter__", "__defineSetter__", "__lookupGetter__", "globalThis", "window", "document"}
FORBIDDEN_NODES = {"WhileStatement", "DoWhileStatement", "NewExpression", "ThisExpression", "TryStatement", "ThrowStatement",
                   "ClassDeclaration", "ClassExpression", "ClassBody", "MethodDefinition", "ImportDeclaration", "ExportNamedDeclaration",
                   "ExportDefaultDeclaration", "ExportAllDeclaration", "AwaitExpression", "YieldExpression", "TaggedTemplateExpression",
                   "WithStatement", "LabeledStatement", "DebuggerStatement", "ForInStatement", "SwitchStatement", "Import", "Super", "MetaProperty"}
SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT = 0.08 * render.HEIGHT, 0.86 * render.HEIGHT, 0.88 * render.WIDTH


def _walk(node, visit, parent=None):
    if isinstance(node, list):
        for child in node:
            _walk(child, visit, parent)
    elif hasattr(node, "type"):
        visit(node, parent)
        for key, value in node.__dict__.items():
            if key not in ("range", "loc") and (hasattr(value, "type") or isinstance(value, list)):
                _walk(value, visit, node)


def _declared(tree) -> set[str]:
    names: set[str] = set()

    def collect(pattern):
        if pattern is None:
            return
        if pattern.type == "Identifier":
            names.add(pattern.name)
        elif pattern.type == "ArrayPattern":
            for el in pattern.elements:
                collect(el)
        elif pattern.type == "ObjectPattern":
            for prop in pattern.properties:
                collect(prop.value if prop.type == "Property" else prop.argument)
        elif pattern.type == "AssignmentPattern":
            collect(pattern.left)
        elif pattern.type == "RestElement":
            collect(pattern.argument)

    def visit(node, _parent):
        if node.type == "VariableDeclarator":
            collect(node.id)
        elif node.type in ("FunctionExpression", "ArrowFunctionExpression", "FunctionDeclaration"):
            for p in node.params:
                collect(p)
            if node.type == "FunctionDeclaration" and node.id:
                names.add(node.id.name)

    _walk(tree, visit)
    return names


def static_check(code: str, required_templates: tuple[str, ...] = ()) -> list[str]:
    """Liste des violations de la liste blanche (vide = conforme). `code` = corps de `build(S)`.
    `required_templates` : gabarits que le plan DOIT instancier (`layout` du storyboard)."""
    if len(code) > MAX_CODE_CHARS:
        return [f"code trop long ({len(code)} caractères, maximum {MAX_CODE_CHARS})"]
    try:
        tree = esprima.parseScript("(function(S){\n" + code + "\n})", {"tolerant": False})
    except esprima.Error as exc:
        return [f"syntaxe invalide (ES2017 seulement : pas de ?. ni ??) : {exc}"]
    errors: list[str] = []
    allowed = ALLOWED_GLOBALS | _declared(tree)

    def visit(node, parent):
        t = node.type
        if t in FORBIDDEN_NODES:
            errors.append(f"construction interdite : {t}")
        elif t == "Identifier":
            is_prop = parent is not None and ((parent.type == "MemberExpression" and parent.property is node and not parent.computed)
                                              or (parent.type == "Property" and parent.key is node and not parent.computed and not parent.shorthand))
            if not is_prop and node.name not in allowed:
                errors.append(f"identifiant interdit : {node.name}")
        elif t == "MemberExpression":
            prop = node.property
            if not node.computed and prop.name in FORBIDDEN_PROPS:
                errors.append(f"propriété interdite : {prop.name}")
            if node.computed:
                if prop.type == "Literal" and isinstance(prop.value, str) and prop.value in FORBIDDEN_PROPS:
                    errors.append(f"propriété interdite : {prop.value}")
                elif prop.type == "Literal" and isinstance(prop.value, str):
                    pass
                elif prop.type in ("TemplateLiteral",) or (prop.type == "BinaryExpression" and prop.operator == "+" and _has_string(prop)):
                    errors.append("accès dynamique par chaîne construite interdit")
            if node.object.type == "Identifier" and node.object.name == "Math" and not node.computed and prop.name not in ALLOWED_MATH:
                errors.append(f"Math.{prop.name} interdit (hasard : utiliser hash(a, b))")
        elif t == "UnaryExpression" and node.operator == "delete":
            errors.append("delete interdit")
        elif t == "ForStatement" and node.test is None:
            errors.append("boucle for sans condition d'arrêt interdite")
        elif t == "AssignmentExpression" and node.left.type == "Identifier" and node.left.name in ALLOWED_GLOBALS:
            errors.append(f"écrasement de {node.left.name} interdit")

    _walk(tree, visit)
    if required_templates:
        used: set[str] = set()

        def collect(node, _parent):
            if (node.type == "CallExpression" and node.callee.type == "MemberExpression" and not node.callee.computed
                    and getattr(node.callee.object, "name", None) == "S" and node.callee.property.name == "template"
                    and node.arguments and node.arguments[0].type == "Literal"):
                used.add(str(node.arguments[0].value))

        _walk(tree, collect)
        for name in required_templates:
            if name not in used:
                errors.append(f"ce plan a le layout « {name} » : il doit appeler S.template('{name}', {{...}}) (utilisés : {sorted(used) or 'aucun'})")
    return sorted(set(errors))


def _has_string(node) -> bool:
    if node.type == "Literal":
        return isinstance(node.value, str)
    if node.type == "TemplateLiteral":
        return True
    if node.type == "BinaryExpression":
        return _has_string(node.left) or _has_string(node.right)
    return False


def plan_module(code: str, plan_id: str, duration: float, anchors: dict[str, float]) -> str:
    """Timeline autonome contenant ce seul plan (pour l'essai) ; le même gabarit sert à l'assemblage final."""
    return ("Faceloop.define({duration:%s,narration:[],plans:[{id:%s,duration:%s,anchors:%s,transition:{},build:function(S){\n%s\n}}]});\n"
            % (json.dumps(duration), json.dumps(plan_id), json.dumps(duration), json.dumps(anchors), code))


def _overlap(a: dict, b: dict) -> float:
    w = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    h = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / max(1.0, min((a["x1"] - a["x0"]) * (a["y1"] - a["y0"]), (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])))


def analyse_probe(report: dict) -> tuple[list[str], list[str]]:
    """(erreurs, avertissements) pour une image sondée. Les petits textes (interface du téléphone, < 26 px de haut)
    sont ignorés : ils ne sont pas des mots-clés."""
    errors, warnings, t = [], [], report["t"]
    big = [x for x in report["texts"] if x["alpha"] > 0.5 and (x["y1"] - x["y0"]) >= 26]
    for x in big:
        cut = (x["x0"] < -4 or x["x1"] > render.WIDTH + 4 or x["y0"] < -4 or x["y1"] > render.HEIGHT + 4)
        visible = x["x1"] > 0 and x["x0"] < render.WIDTH and x["y1"] > 0 and x["y0"] < render.HEIGHT
        if cut and visible:
            errors.append(f"t={t:.1f}s : le texte « {x['s']} » est coupé par le bord de l'écran")
        elif visible and (x["y0"] < SAFE_TOP or x["y1"] > SAFE_BOTTOM or x["x1"] > SAFE_RIGHT) and (x["y1"] - x["y0"]) >= 40:
            warnings.append(f"t={t:.1f}s : « {x['s']} » dans une zone d'interface de plateforme")
    for i, a in enumerate(big):
        for b in big[i + 1:]:
            if a["s"] != b["s"] and _overlap(a, b) > 0.25:
                errors.append(f"t={t:.1f}s : « {a['s']} » et « {b['s']} » se chevauchent")
    if report["ms"] > FRAME_BUDGET_MS:
        errors.append(f"t={t:.1f}s : image trop lente ({report['ms']:.0f} ms, budget {FRAME_BUDGET_MS} ms)")
    errors.extend(f"erreur JS : {e}" for e in report["errors"])
    return errors, warnings



def sample_times(duration: float, anchors: dict[str, float]) -> list[float]:
    base = [0.05, duration * 0.25, duration * 0.5, duration * 0.75, duration - 0.1]
    around = [a + d for a in anchors.values() for d in (0.05, 0.6)]
    return sorted({round(min(max(t, 0.0), duration - 0.05), 2) for t in base + around})


async def trial_async(module_js: str, duration: float, anchors: dict[str, float]) -> dict:
    from playwright.async_api import async_playwright

    errors: list[str] = []
    warnings: list[str] = []
    coverages: list[tuple[float, float]] = []
    with tempfile.TemporaryDirectory() as tmp:
        timeline = Path(tmp) / "plan.timeline.js"
        timeline.write_text(module_js, encoding="utf-8")
        stage = render.build_stage_html(timeline, tmp)
        async with async_playwright() as p:
            browser = None
            try:
                browser, page = await asyncio.wait_for(render.open_page(p, stage), TRIAL_TIMEOUT_S)
                build_errors = await page.evaluate("window.__buildErrors || []")
                errors.extend(f"construction du plan : {e['message']}" for e in build_errors)
                if not await page.evaluate("typeof window.VIDEO === 'object'"):
                    errors.append("le plan n'a pas défini la vidéo")
                else:
                    for t in sample_times(duration, anchors):
                        report = await asyncio.wait_for(page.evaluate("(t)=>probeFrame(t)", t), TRIAL_TIMEOUT_S)
                        e, w = analyse_probe(report)
                        errors.extend(e)
                        warnings.extend(w)
                        coverages.append((report["t"], report.get("coverage", {"total": 1.0, "bands": [1.0] * 8})))
                    errors.extend(f"erreur d'exécution : {m}" for m in await page.evaluate("window.__runtimeErrors || []"))
                    first = [c["total"] for t, c in coverages if t <= 0.1]
                    if first and first[0] < FIRST_FRAME_MIN:
                        errors.append("premier plan vide : le sujet principal doit être visible dès la première image (t = 0), sans attendre un `appear`")
                    sparse = [t for t, c in coverages if t > 0.3 and c["total"] < MIN_COVERAGE]
                    # Remplissage vertical : au moins 3 des 6 bandes centrales (y 240 -> 1680) doivent contenir quelque chose (calibré sur la vitrine
                    # validée à l'œil : 4 à 7 bandes ; et sur les gabarits : 2 à 5 bandes selon l'instant)
                    lopsided = [t for t, c in coverages if t > 0.3 and sum(1 for b in c["bands"][1:7] if b >= BAND_MIN) < 3]
                    if len(lopsided) >= max(2, round(len(coverages) * 0.6)):
                        errors.append("contenu mal réparti : de grandes zones verticales de l'écran sont vides aux instants "
                                      + ", ".join(f"{t:.1f}s" for t in lopsided[:4]) + " : centre la composition, agrandis les éléments, "
                                      "utilise un gabarit (S.template) ou un décor plein cadre")
                    if len(sparse) >= 2:
                        errors.append("cadre presque vide aux instants " + ", ".join(f"{t:.1f}s" for t in sparse[:4])
                                      + " : remplis l'écran (décor, éléments plus grands, caméra plus serrée)")
                    t_mid = duration * 0.4
                    first = await render.grab(page, t_mid, "png")
                    await render.grab(page, duration * 0.8, "png")
                    again = await render.grab(page, t_mid, "png")
                    if first != again:
                        errors.append("rendu non déterministe : deux rendus du même instant diffèrent")
            except asyncio.TimeoutError:
                errors.append(f"exécution trop longue (plus de {TRIAL_TIMEOUT_S} s) : boucle infinie ou calcul trop lourd ?")
            except Exception as exc:  # noqa: BLE001 — l'essai ne doit jamais faire tomber le pipeline
                errors.append(f"essai Chromium impossible : {str(exc)[:200]}")
            finally:
                if browser is not None:
                    try:
                        await asyncio.wait_for(browser.close(), 10)
                    except Exception:  # noqa: BLE001
                        pass
    return {"errors": sorted(set(errors)), "warnings": sorted(set(warnings))}


def validate_plan(code: str, plan_id: str, duration: float, anchors: dict[str, float], layout: str = "scene") -> dict:
    """{ok, stage, errors, warnings}. `stage` : 'static' ou 'trial' (où ça a échoué). `layout` : gabarit exigé ('scene' = libre)."""
    static = static_check(code, () if layout in ("scene", "", None) else (layout,))
    if static:
        return {"ok": False, "stage": "static", "errors": static, "warnings": []}
    result = asyncio.run(trial_async(plan_module(code, plan_id, duration, anchors), duration, anchors))
    return {"ok": not result["errors"], "stage": "trial", **result}
