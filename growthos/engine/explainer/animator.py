"""Animateur : un plan du storyboard -> code JS contre l'API du runtime, validé (`validate.py`), au plus 2 corrections.

On garde la MEILLEURE version : un plan validé n'est jamais remplacé par une correction qui régresse. Un plan qui échoue
après les itérations est renvoyé en échec avec ses raisons (le pipeline le remplace alors par le repli Pillow, écrit
au rapport).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import llm, prompts, validate

MAX_REPAIRS = 2
PLANS_DIR = Path(__file__).resolve().parent / "reference" / "plans"
# Plans de référence donnés en exemple : (fichier, brief). Le brief a le même format que celui d'un vrai plan.
REFERENCES = {
    "chat-send": {"duration": 7.0, "anchors": {"send": 3.4}, "narration": "Elle appuie sur Envoyer.",
                  "intent": "montrer qu'un message est tapé puis envoyé",
                  "visual": "Gros plan sur un téléphone : le message « On mange ce soir ? » se tape lettre par lettre ; sur « Envoyer » le bouton s'enfonce, la bulle part, le mot-clé ENVOYER apparaît en haut.",
                  "camera": "zoom très lent vers l'écran"},
    "network-journey": {"duration": 8.0, "anchors": {"go": 1.2}, "narration": "Le signal part vers l'antenne puis le réseau.",
                        "intent": "suivre trois morceaux de message du téléphone à l'antenne puis le long du sol",
                        "visual": "Ville de nuit, antenne ; trois blocs #1 #2 #3 quittent un petit téléphone à gauche, montent à l'antenne (ondes radio), redescendent et filent vers la droite ; légende ANTENNE.",
                        "camera": "suit les paquets, glisse lentement vers la droite"},
    "house-room": {"duration": 7.0, "anchors": {"send": 3.4}, "narration": "Awa écrit à son amie, à Dakar. Elle appuie sur envoyer.",
                   "intent": "installer le lieu et le personnage, puis s'approcher du geste d'envoi",
                   "visual": "Maison en coupe de nuit remplissant l'écran, Awa assise sur le canapé avec son téléphone ; mot-clé DAKAR en haut qui disparaît juste avant « envoyer » ; sur « envoyer » un petit rebond du personnage et un bruit.",
                   "camera": "plan large puis zoom lent vers le personnage"},
    "data-reveal": {"duration": 7.0, "anchors": {"start": 1.0, "end": 5.0, "bars": 2.0}, "narration": "Mille euros à dix pour cent par an : après dix ans, on dépasse deux mille six cents.",
                    "intent": "montrer une croissance exponentielle avec un chiffre et des barres",
                    "visual": "Gabarits bignumber (de 1 000 € à 2 594 €, légende « après 10 ans ») et bars (11 barres, années 0 à 10).",
                    "camera": "léger zoom continu"},
    "equation-steps": {"duration": 8.0, "anchors": {"s1": 2.0, "s2": 3.8, "s3": 5.6}, "narration": "On enlève trois des deux côtés, on divise par deux, et x vaut quatre.",
                       "intent": "résoudre 2x + 3 = 11 étape par étape",
                       "visual": "Gabarit equation : lignes 2x + 3 = 11 / 2x = 11 − 3 (note « − 3 des deux côtés ») / 2x = 8 / x = 4 (note « ÷ 2 des deux côtés »), chacune sur sa phrase.",
                       "camera": "léger zoom"},
    "geometry-golden": {"duration": 7.0, "anchors": {"cut": 2.0, "name": 3.5}, "narration": "Coupe un segment en deux, de façon que le tout sur le grand morceau égale le grand morceau sur le petit : c'est le nombre d'or.",
                        "intent": "montrer la coupe d'un segment selon une proportion",
                        "visual": "Gabarit segment (a + b, coupe sur « coupe », étiquettes a et b) ; le mot-clé LE NOMBRE D'OR en haut sur « nombre d'or ».",
                        "camera": "léger zoom"},
}


def plan_brief(plan: dict, duration: float, anchors: dict[str, float], narration_text: str, topic: str, bible: dict, world: dict) -> str:
    anchors_txt = {a["id"]: {"mot": a["text"], "seconde": anchors.get(a["id"])} for a in plan.get("anchors", [])}
    return json.dumps({"sujet": topic, "plan": plan["id"], "duree_s": duration, "narration_du_plan": narration_text, "intention": plan["intent"],
                       "brief_visuel": plan["visual"], "camera": plan["camera"], "ancres": anchors_txt, "monde": world, "bible": bible},
                      ensure_ascii=False, indent=1)


def system_prompt() -> str:
    parts = [prompts.load("animator"), prompts.load("runtime-api"), "\n# Plans de référence\n"]
    for name, spec in REFERENCES.items():
        brief = json.dumps({"plan": name, "duree_s": spec["duration"], "narration_du_plan": spec["narration"], "intention": spec["intent"],
                            "brief_visuel": spec["visual"], "camera": spec["camera"],
                            "ancres": {k: {"seconde": v} for k, v in spec["anchors"].items()}}, ensure_ascii=False)
        code = (PLANS_DIR / f"{name}.plan.js").read_text(encoding="utf-8")
        parts.append(f"## Exemple : {name}\nBrief :\n{brief}\n\nCode :\n```js\n{code}```\n")
    return "\n".join(parts)


def animate_plan(spend: llm.Spend, system: str, brief: str, plan_id: str, duration: float, anchors: dict[str, float]) -> dict:
    """Renvoie {id, ok, code, attempts, errors, warnings, history}. `ok` False = plan à remplacer par le repli."""
    best, history, errors = None, [], []
    code = ""
    for attempt in range(MAX_REPAIRS + 1):
        try:
            user = brief if not errors else (
                brief + "\n\nTon code précédent :\n```js\n" + code + "\n```\nIl a échoué à la validation. Corrige exactement ces problèmes et renvoie le plan complet :\n- "
                + "\n- ".join(errors[:12]))
            text = llm.complete(spend, f"animator:{plan_id}#{attempt + 1}", llm.ANIMATOR_MODEL, system, user, max_tokens=12000, effort="medium")
        except llm.BudgetExceeded as exc:
            history.append({"attempt": attempt + 1, "stage": "budget", "errors": [str(exc)]})
            break
        except RuntimeError as exc:
            history.append({"attempt": attempt + 1, "stage": "llm", "errors": [str(exc)]})
            errors = [str(exc)]
            continue
        code = llm.extract_code(text)
        result = validate.validate_plan(code, plan_id, duration, anchors)
        history.append({"attempt": attempt + 1, "stage": result["stage"], "ok": result["ok"], "errors": result["errors"][:8], "warnings": result["warnings"][:5]})
        if result["ok"]:
            best = {"code": code, "warnings": result["warnings"], "attempt": attempt + 1}
            break
        errors = result["errors"]
    if best:
        return {"id": plan_id, "ok": True, "code": best["code"], "attempts": best["attempt"], "errors": [], "warnings": best["warnings"], "history": history}
    return {"id": plan_id, "ok": False, "code": code, "attempts": len(history), "errors": errors, "warnings": [], "history": history}


def improve_plan(spend: llm.Spend, system: str, brief: str, code: str, issues: str, plan_id: str, duration: float, anchors: dict[str, float]) -> dict:
    """Retouche d'un plan déjà valide d'après les corrections du critique. Renvoie {ok, code, errors} : un résultat qui
    ne valide pas est écarté par l'appelant (on garde la version précédente)."""
    user = (brief + "\n\nCode actuel du plan :\n```js\n" + code + "\n```\nLe critique visuel demande ces retouches. Applique-les sans casser "
            "le reste (mêmes ancres, mêmes éléments utiles) et renvoie le plan complet :\n" + issues)
    try:
        new = llm.extract_code(llm.complete(spend, f"improve:{plan_id}", llm.ANIMATOR_MODEL, system, user, max_tokens=12000, effort="medium"))
    except RuntimeError as exc:   # budget atteint, refus, réponse tronquée : on garde la version actuelle
        return {"id": plan_id, "ok": False, "code": code, "errors": [str(exc)]}
    result = validate.validate_plan(new, plan_id, duration, anchors)
    return {"id": plan_id, "ok": result["ok"], "code": new if result["ok"] else code, "errors": result["errors"], "warnings": result["warnings"]}


def animate_all(spend: llm.Spend, jobs: list[dict], workers: int = 3) -> list[dict]:
    """`jobs` : [{brief, plan_id, duration, anchors}]. Les plans sont indépendants : ils s'animent en parallèle."""
    system = system_prompt()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs)))) as pool:
        futures = [pool.submit(animate_plan, spend, system, j["brief"], j["plan_id"], j["duration"], j["anchors"]) for j in jobs]
        return [f.result() for f in futures]
