"""Intérêts composés : capital, taux annuel, durée -> narration, storyboard et gabarits, calculés exactement (centimes arrondis
chaque année, comme un relevé bancaire), sans modèle. Tous les chiffres affichés ou dits viennent du calcul."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

LIMITS = {"capital": (1, 1_000_000), "rate": (0.5, 30), "years": (5, 30)}
CENT = Decimal("0.01")

TEXT = {
    "fr": {
        "topic": "Les intérêts composés", "unit": {"eur": "euros", "usd": "dollars"}, "sym": {"eur": "€", "usd": "$"},
        "lines": [
            "Tu places {c} {u} à {r} % par an. Que se passe-t-il avec le temps ?",
            "Au bout d'un an, tu gagnes {g1} {u} : ton total passe à {t1} {u}.",
            "La deuxième année, les {r} % s'appliquent sur {t1} {u}, pas sur {c}.",
            "Tu gagnes donc {g2} {u}, et ton total monte à {t2} {u}.",
            "La troisième année, {r} % de {t2} {u} font {g3} {u} : tu atteins {t3} {u}.",
            "Chaque gain s'ajoute au capital, et rapporte à son tour.",
            "Avec des intérêts simples, tu gagnerais {g1} {u} chaque année, toujours la même somme.",
            "Avec des intérêts composés, le gain grandit, parce que la base grandit.",
            "Sur {n} ans, ton capital passe de {c} à {tn} {u}, contre {sn} {u} avec des intérêts simples.",
            "Plus tu laisses faire le temps, plus la courbe s'incurve vers le haut.",
            "L'intérêt composé peut travailler pour toi quand tu épargnes, ou contre toi quand tu empruntes.",
        ],
        "title": "L'intérêt composé", "sub": "quand ton argent travaille", "hello": "Salut !",
        "per_year": "à {r} % par an", "year": "année {k}", "start": "Départ", "y": "An {k}", "growing": "Le capital grandit",
        "simple": "Simples", "compound": "Composés", "chart": "L'argent à {r} % par an", "xlabel": "Années", "ylabel": "Capital ({s})",
        "end_title": "Épargner ou emprunter", "end_sub": "comprendre pour choisir", "end_say": "Pour toi !",
        "w": {"ans": "ans", "third": "troisième", "simples": "simples", "same": "même", "compounds": "composés", "base": "base", "curve": "courbe",
              "save": "épargnes", "borrow": "empruntes", "gain": "gagnes", "total": "total", "apply": "deuxième", "rises": "monte", "reach": "atteins"},
    },
    "en": {
        "topic": "Compound interest", "unit": {"eur": "euros", "usd": "dollars"}, "sym": {"eur": "€", "usd": "$"},
        "lines": [
            "You invest {c} {u} at {r} percent a year. What happens over time?",
            "After one year, you earn {g1} {u}: your total becomes {t1} {u}.",
            "In the second year, the {r} percent applies to {t1} {u}, not to {c}.",
            "So you earn {g2} {u}, and your total rises to {t2} {u}.",
            "In the third year, {r} percent of {t2} {u} is {g3} {u}: you reach {t3} {u}.",
            "Each gain is added to the capital, and earns in turn.",
            "With simple interest, you would earn {g1} {u} every year, always the same amount.",
            "With compound interest, the gain grows, because the base grows.",
            "Over {n} years, your capital goes from {c} to {tn} {u}, versus {sn} {u} with simple interest.",
            "The more you let time work, the more the curve bends upward.",
            "Compound interest can work for you when you save, or against you when you borrow.",
        ],
        "title": "Compound interest", "sub": "when your money works", "hello": "Hi!",
        "per_year": "at {r}% a year", "year": "year {k}", "start": "Start", "y": "Year {k}", "growing": "The capital grows",
        "simple": "Simple", "compound": "Compound", "chart": "Money at {r}% a year", "xlabel": "Years", "ylabel": "Capital ({s})",
        "end_title": "Save or borrow", "end_sub": "understand to choose", "end_say": "For you!",
        "w": {"ans": "years", "third": "third", "simples": "simple", "same": "same", "compounds": "compound", "base": "base", "curve": "curve",
              "save": "save", "borrow": "borrow", "gain": "earn", "total": "total", "apply": "applies", "rises": "rises", "reach": "reach"},
    },
}


def _dec(x) -> Decimal:
    return Decimal(str(x))


def compute(capital, rate, years: int) -> dict:
    """Totaux calculés en précision pleine (100 x 1,10^10 = 259,37), arrondis au centime SEULEMENT pour l'affichage ; chaque gain
    affiché est la différence des totaux arrondis : les additions montrées à l'écran tombent toujours juste."""
    c, r = _dec(capital), _dec(rate) / 100
    exact = [c * (1 + r) ** k for k in range(years + 1)]
    totals = [x.quantize(CENT, rounding=ROUND_HALF_UP) for x in exact]
    gains = [totals[k + 1] - totals[k] for k in range(years)]
    simple = (c + c * r * years).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"totals": totals, "gains": gains, "simple_total": simple}


def _fmt(x: Decimal, lang: str) -> str:
    """Entier sans décimales ; sinon 2 décimales ; séparateur propre à la langue (« 133,10 » / « 133.10 »)."""
    x = x.quantize(CENT)
    s = f"{int(x):d}" if x == x.to_integral_value() else f"{x:.2f}"
    return s.replace(".", ",") if lang == "fr" else s


def check(params: dict) -> dict:
    out = {}
    for key, (lo, hi) in LIMITS.items():
        if key not in params:
            raise ValueError(f"paramètre manquant : {key}")
        try:
            v = float(params[key])
        except (TypeError, ValueError):
            raise ValueError(f"{key} doit être un nombre") from None
        if not lo <= v <= hi:
            raise ValueError(f"{key} doit être entre {lo} et {hi} (reçu {v})")
        out[key] = v
    out["years"] = int(out["years"])
    out["currency"] = params.get("currency", "eur")
    if out["currency"] not in ("eur", "usd"):
        raise ValueError("currency doit valoir eur ou usd")
    return out


def build(params: dict, lang: str = "fr") -> dict:
    if lang not in TEXT:
        raise ValueError(f"langue non prise en charge : {lang!r} ({sorted(TEXT)})")
    p, T = check(params), TEXT[lang]
    n, cur = p["years"], p["currency"]
    calc = compute(p["capital"], p["rate"], n)
    tot, gain = calc["totals"], calc["gains"]

    def f(x):
        return _fmt(x, lang)

    fields = {"c": f(tot[0]), "r": _fmt(_dec(p["rate"]), lang), "u": T["unit"][cur], "g1": f(gain[0]), "g2": f(gain[1]), "g3": f(gain[2]),
              "t1": f(tot[1]), "t2": f(tot[2]), "t3": f(tot[3]), "n": str(n), "tn": f(tot[n]), "sn": f(calc["simple_total"])}
    lines = [t.format(**fields) for t in T["lines"]]
    sym, w = T["sym"][cur], T["w"]

    def anchor(aid, text, occurrence=1):
        return {"id": aid, "text": text, "occurrence": occurrence}

    # Les chiffres servent d'ancres : la voix les dit à l'instant où le graphisme les montre.
    plans = [
        {"id": "p1", "lines": [0], "layout": "title", "anchors": []},
        {"id": "p2", "lines": [1], "layout": "bignumber", "anchors": [anchor("start", w["gain"]), anchor("total", w["total"])]},
        {"id": "p3", "lines": [2, 3], "layout": "equation", "anchors": [anchor("base", w["apply"]), anchor("y2", w["rises"])]},
        {"id": "p4", "lines": [4, 5], "layout": "bars", "anchors": [anchor("third", w["third"]), anchor("t3", w["reach"])]},
        {"id": "p5", "lines": [6, 7], "layout": "compare", "anchors": [anchor("simple", w["simples"]), anchor("same", w["same"]),
                                                                       anchor("compound", w["compounds"]), anchor("base", w["base"])]},
        {"id": "p6", "lines": [8, 9], "layout": "linechart", "anchors": [anchor("axes", w["ans"]), anchor("curve", w["curve"])]},
        {"id": "p7", "lines": [10], "layout": "title", "anchors": [anchor("save", w["save"]), anchor("borrow", w["borrow"])]},
    ]
    for pl in plans:
        pl.update({"intent": "expliquer l'intérêt composé par un calcul exact", "visual": f"gabarit {pl['layout']} rempli avec les montants calculés",
                   "camera": "léger zoom", "transitionOut": "dip", "claims": []})
    storyboard = {"version": "explainer-storyboard:v1", "truthMode": "fact", "world": {"metaphor": "un capital qui grandit année après année"},
                  "bible": {"characters": [], "objects": []}, "plans": plans}

    curve = [float(t) for t in tot[: n + 1]]
    whole = tot[1] == tot[1].to_integral_value()
    composition = {"plans": [
        {"id": "p1", "template": "title", "params": {"text": T["title"], "sub": T["sub"], "t": 0},
         "guide": {"who": "awa", "side": "left", "size": 0.8, "poses": [{"t": 0, "pose": "wave"}], "say": [{"t": 0.3, "text": T["hello"], "until": 1.8}]}},
        {"id": "p2", "template": "bignumber", "params": {"from": float(tot[0]), "to": float(tot[1]), "t0": "@start", "t1": "@total", "suffix": f" {sym}",
                                                         "decimals": 0 if whole else 2, "label": T["per_year"].format(r=fields["r"]), "labelT": "@total"}, "guide": None},
        {"id": "p3", "template": "equation", "params": {"lines": [
            {"text": f"{fields['c']} + {fields['g1']} = {fields['t1']}", "t": 0, "note": T["year"].format(k=1)},
            {"text": f"{fields['r']} % × {fields['t1']} = {fields['g2']}", "t": "@base", "note": T["year"].format(k=2)},
            {"text": f"{fields['t1']} + {fields['g2']} = {fields['t2']}", "t": "@y2"}]}, "guide": None},
        {"id": "p4", "template": "bars", "params": {"values": [float(x) for x in tot[:4]], "labels": [T["start"]] + [T["y"].format(k=k) for k in (1, 2, 3)],
                                                     "t0": "@third", "t1": "@t3", "title": T["growing"], "readout": f"{fields['t3']} {sym}", "readoutT": "@t3"}, "guide": None},
        {"id": "p5", "template": "compare", "params": {
            "left": {"title": T["simple"], "items": [f"+{fields['g1']} {sym}"] * 3, "times": [0.4, "@simple", "@same"]},
            "right": {"title": T["compound"], "items": [f"+{f(gain[0])} {sym}", f"+{f(gain[1])} {sym}", f"+{f(gain[2])} {sym}"],
                      "times": ["@compound", "@compound+0.9", "@base"]}}, "guide": None},
        {"id": "p6", "template": "linechart", "params": {"values": curve, "t0": "@axes", "t1": "@curve+1.2", "title": T["chart"].format(r=fields["r"]),
                                                          "xlabel": T["xlabel"], "ylabel": T["ylabel"].format(s=sym)}, "guide": None},
        {"id": "p7", "template": "title", "params": {"text": T["end_title"], "sub": T["end_sub"]},
         "guide": {"who": "awa", "side": "left", "size": 0.8, "poses": [{"t": 0, "pose": "point"}, {"t": "@borrow", "pose": "cheer"}],
                   "say": [{"t": "@save", "text": T["end_say"], "until": "@save+1.6"}]}},
    ]}
    return {"topic": T["topic"], "lines": lines, "storyboard": storyboard, "composition": composition,
            "numbers": {"totals": [str(x) for x in tot[: n + 1]], "simple": str(calc["simple_total"])}}
