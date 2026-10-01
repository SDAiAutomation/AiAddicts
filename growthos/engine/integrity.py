"""Intégrité du contenu (Phase 5.3) : des contrôles DÉTERMINISTES, étroits, sans LLM ni réseau.

Ce que le modèle écrit peut être faux d'une façon que le spectateur ne peut pas voir : un calcul erroné
(« 40 $ par semaine, soit 1 920 $ par an » : 40 x 52 = 2 080), une projection d'investissement présentée
sans hypothèse, une statistique inventée (« la plupart des envies disparaissent »), un CTA qui promet une
ressource qui n'existe pas. Chaque détecteur ci-dessous ne reconnaît qu'une forme BIEN délimitée ; hors de
ces formes, il se tait (un faux positif sur une vidéo publiée est pire qu'un oubli). Ce n'est PAS un
moteur de calcul symbolique ni un vérificateur de faits : aucune recherche externe.

Les indices de blocs sont à base 0. Chaque détecteur retourne des dicts {block, ...} ; la sévérité et le
message sont décidés par `engine/retention.py`.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------------------------
# Nombres
# ---------------------------------------------------------------------------------------------

_NUM = r"\d[\d,]*(?:\.\d+)?"
_UNIT_FACTOR_TO_YEAR = {"day": 365, "week": 52, "month": 12, "year": 1}
_UNIT_ALIASES = {"daily": "day", "weekly": "week", "monthly": "month", "yearly": "year", "annually": "year"}
_RELATION_CUES = (
    " is ", " are ", " equals ", "=", " that's ", " that is ", " adds up to ", " add up to ", " becomes ",
    " become ", " comes to ", " works out ", " turns into ", " amounts to ", " totals ", " total ", " makes ",
    " means ", "→", " so ", " which is ", " add ", " adds ", " gives ", " give ",
)
# Mots autorisés ENTRE deux taux pour que ce soit une relation (« 5 $ par jour, soit 1 825 $ par an ») : tout autre
# mot (« coffee », « rent ») signale deux quantités sans rapport.
_RELATION_FILLER = frozenset((
    "is", "are", "equals", "that's", "that", "adds", "add", "up", "to", "becomes", "become", "comes", "works", "out",
    "turns", "into", "amounts", "totals", "total", "makes", "means", "so", "which", "and", "about", "roughly", "around",
    "only", "gives", "give", "you", "it", "this", "will", "can", "could", "would", "get", "just", "simply", "or", "than",
))


def _normalize(text: str) -> str:
    from . import retention  # import tardif : retention importe ce module

    text = retention.normalize_number_words(retention._expand_k(str(text or "")))
    text = re.sub(r"(?<=\d) (?=\d{3}\b)", "", text)  # « 1 000 » -> « 1000 »
    text = re.sub(r"/\s*(day|week|month|year)", r" per ", text, flags=re.IGNORECASE)  # "$5/day" -> "$5 per day"
    return text.replace("’", "'")


def _to_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def _close(actual: float, expected: float, tolerance: float) -> bool:
    return expected != 0 and abs(actual - expected) <= max(1.0, abs(expected) * tolerance)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# ---------------------------------------------------------------------------------------------
# Arithmétique reconnaissable
# ---------------------------------------------------------------------------------------------

_RATE_RE = re.compile(
    rf"\$?(?P<amt>{_NUM})(?:\s+(?:dollars?|euros?|bucks))?(?P<gap>(?:\s+[A-Za-z]+){{0,2}}?)"
    r"\s+(?:(?:a|per|each|every)\s+(?P<unit>day|week|month|year)|(?P<alias>daily|weekly|monthly|yearly|annually))\b",
    re.IGNORECASE,
)
_GOAL_RE = re.compile(
    rf"\b(?:reach|hit|get to|have|build|save up|accumulate)\b[^.!?]{{0,40}}?\$?(?P<goal>{_NUM})"
    r"[^.!?]{0,40}?\b(?:in|within|after)\s+(?:about |around |roughly |approximately )?(?P<n>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_PERCENT_OF_RE = re.compile(
    rf"(?P<p>\d+(?:\.\d+)?)\s?(?:%|percent)\s+of\s+(?:(?:a|an|the|your|that|this|those)\s+)?(?:[A-Za-z]+\s+){{0,2}}?\$?(?P<base>{_NUM})",
    re.IGNORECASE,
)
_RESULT_CUE_RE = re.compile(r"\b(?:is|=|equals|means|gives|comes to|saves?|leaves?)\b", re.IGNORECASE)
_LEFT_RE = re.compile(r"(?:\b(?:left|leaving|leaves|remain(?:s|ing)?|leftover)\b|=)", re.IGNORECASE)
_TOTAL_RE = re.compile(
    r"(?:that's|that is|totals?|in total|altogether|combined|together|adds up to|add up to)\s+(?:about |roughly |only )?\$?(" + _NUM + ")",
    re.IGNORECASE,
)
_CONTRIB_CUE = re.compile(r"\b(?:put in|contribut\w*|deposit\w*|paid in|total of|invested a total of)\b", re.IGNORECASE)
_CONTRIB_HORIZON = re.compile(r"\b(?:over|in|after|for)\s+(?:about |around |roughly )?(?P<n>\d+(?:\.\d+)?)\s+(?P<unit>years?|months?)\b", re.IGNORECASE)


def _contribution_claim(sentence: str) -> tuple[float, float, str] | None:
    """(total annoncé, durée, unité) pour « you put in $73,000 over 40 years » ; None sinon. Le total est le DERNIER
    montant avant la durée (« $1,825 per year and $54,750 over 30 years » -> 54 750), jamais un taux annuel."""
    cue = _CONTRIB_CUE.search(sentence)
    if not cue:
        return None
    horizon = _CONTRIB_HORIZON.search(sentence, cue.end())
    if not horizon:
        return None
    amounts = []
    for m in re.finditer(rf"\$({_NUM})", sentence[cue.end():horizon.start()]):
        tail = sentence[cue.end() + m.end(): cue.end() + m.end() + 12].lower()
        if re.match(r"\s*(?:per|a|each|every)\s+(?:day|week|month|year)", tail):
            continue
        amounts.append(_to_float(m.group(1)))
    if not amounts:
        return None
    return amounts[-1], float(horizon.group("n")), horizon.group("unit").lower()


def _money_numbers(text: str) -> list[tuple[int, float]]:
    """Montants d'une phrase : seulement les nombres MARQUÉS comme une somme (« $250 », « 250 dollars ») quand la
    phrase en contient ; sinon aucun (« four small buys » n'est pas un montant). Hors taux (« par jour »)."""
    candidates: list[tuple[int, float, bool]] = []
    taken = [m.span() for m in _RATE_RE.finditer(text)]
    for m in re.finditer(_NUM, text):
        span = m.span()
        if any(a <= span[0] < b for a, b in taken):
            continue
        after = text[span[1]:span[1] + 14].lower()
        if re.match(r"\s?(?:%|percent|years?|months?|weeks?|days?|hours?|x\b|times)", after):
            continue
        marked = text[max(0, span[0] - 1):span[0]] == "$" or bool(re.match(r"\s?(?:dollars?|euros?|bucks|usd)\b", after))
        candidates.append((span[0], _to_float(m.group(0)), marked))
    if any(c[2] for c in candidates):
        return [(pos, value) for pos, value, marked in candidates if marked]
    return []


def _rates(text: str) -> list[dict]:
    rates = []
    for m in _RATE_RE.finditer(text):
        unit = (m.group("unit") or _UNIT_ALIASES.get((m.group("alias") or "").lower(), "")).lower()
        if unit not in _UNIT_FACTOR_TO_YEAR:
            continue
        gap = (m.group("gap") or "").strip().lower()
        if gap and gap.split()[0] in ("and", "or", "for", "of", "in", "on", "to", "from"):
            continue
        if any(w in ("twice", "thrice", "times", "double", "triple", "two", "three", "four", "2x", "3x", "x") for w in gap.split()):
            continue  # « 450 $ deux fois par mois » : multiplicateur, forme non reconnue
        rates.append({"amt": _to_float(m.group("amt")), "unit": unit, "start": m.start(), "end": m.end()})
    return rates


def _pair_factor(small: str, large: str) -> tuple[float, float] | None:
    """(facteur, tolérance relative) de la petite période vers la grande."""
    table = {
        ("day", "week"): (7, 0.03), ("day", "month"): (30.4, 0.035), ("day", "year"): (365, 0.02),
        ("week", "month"): (4.33, 0.05), ("week", "year"): (52, 0.02), ("month", "year"): (12, 0.02),
    }
    return table.get((small, large))


def _check_rate_pairs(i: int, text: str, issues: list[dict]) -> None:
    for sentence in _sentences(text):
        rates = _rates(sentence)
        for a in range(len(rates)):
            for b in range(a + 1, len(rates)):
                r1, r2 = rates[a], rates[b]
                if r1["unit"] == r2["unit"]:
                    continue
                small, large = sorted((r1, r2), key=lambda r: _UNIT_FACTOR_TO_YEAR[r["unit"]], reverse=True)
                factor = _pair_factor(small["unit"], large["unit"])
                if not factor or large["amt"] < small["amt"]:
                    continue
                first, second = (r1, r2) if r1["start"] < r2["start"] else (r2, r1)
                between = " " + sentence[first["end"]:second["start"]].lower() + " "
                if not any(cue in between for cue in _RELATION_CUES):
                    continue
                residue = _RATE_RE.sub(" ", between)
                residue = re.sub(rf"\$?{_NUM}", " ", residue)
                words = re.findall(r"[a-z']+|=|\u2192", residue)
                if any(w not in _RELATION_FILLER and w not in ("=", "\u2192") for w in words):
                    continue  # un autre sujet entre les deux quantités : pas une relation reconnue
                expected = small["amt"] * factor[0]
                if not _close(large["amt"], expected, factor[1]):
                    issues.append({
                        "block": i, "kind": "rate_conversion",
                        "claim": f"{small['amt']:g} par {small['unit']} -> {large['amt']:g} par {large['unit']}",
                        "expected": round(expected, 2),
                    })


_GOAL_VERB = re.compile(r"\b(?:reach|hit|get to|have|build|save up|accumulate)\b", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(?:in|within|after)\s+(?:about |around |roughly |approximately )?(\d+(?:\.\d+)?)\s+(days?|weeks?|months?|years?)\b", re.IGNORECASE)


def _check_goal(i: int, text: str, issues: list[dict]) -> None:
    for sentence in _sentences(text):
        rates = _rates(sentence)
        time = _TIME_RE.search(sentence)
        if len(rates) != 1 or not time or not _GOAL_VERB.search(sentence):
            continue
        unit = time.group(2).lower().rstrip("s")
        if rates[0]["unit"] != unit:
            continue
        goals = [v for _, v in _money_numbers(sentence) if v != rates[0]["amt"]]
        if len(goals) != 1:
            continue  # zéro ou plusieurs objectifs possibles : forme ambiguë, on se tait
        expected = goals[0] / rates[0]["amt"]
        n = float(time.group(1))
        if not _close(n, expected, 0.12):
            issues.append({"block": i, "kind": "time_to_goal",
                           "claim": f"{goals[0]:g} en {n:g} {unit}s avec {rates[0]['amt']:g} par {unit}", "expected": round(expected, 1)})


def _check_percent_of(i: int, text: str, issues: list[dict]) -> None:
    for sentence in _sentences(text):
        m = _PERCENT_OF_RE.search(sentence)
        if not m:
            continue
        tail = sentence[m.end():]
        cue = _RESULT_CUE_RE.search(tail)
        if not cue:
            continue
        found = re.search(rf"\$?({_NUM})", tail[cue.end():cue.end() + 24])
        if not found:
            continue
        expected = float(m.group("p")) * _to_float(m.group("base")) / 100
        if not _close(_to_float(found.group(1)), expected, 0.02):
            issues.append({"block": i, "kind": "percent_of", "claim": f"{m.group('p')}% de {m.group('base')} = {found.group(1)}",
                           "expected": round(expected, 2)})


def _check_chain(i: int, text: str, prev_text: str, issues: list[dict]) -> None:
    for sentence in _sentences(text):
        nums = _money_numbers(sentence)
        left = _LEFT_RE.search(sentence)
        if left and len(nums) >= 3:
            after = [n for n in nums if n[0] >= left.start()]
            before = [n for n in nums if n[0] < left.start()]
            if after and len(before) >= 2:
                total, items, result = before[0][1], [v for _, v in before[1:]], after[0][1]
                if total >= max(items + [result]) and total >= sum(items):  # le total est bien présent dans la phrase
                    if not _close(result, total - sum(items), 0.01):
                        issues.append({"block": i, "kind": "subtraction_chain",
                                       "claim": f"{total:g} - {sum(items):g} = {result:g}", "expected": round(total - sum(items), 2)})
    for m in _TOTAL_RE.finditer(text):
        if re.match(r"\s*(?:a|per|each|every)\s+(?:day|week|month|year)\b", text[m.end():]):
            continue  # un taux (« 850 par mois »), pas un total : forme non reconnue
        before = [v for pos, v in _money_numbers(text[:m.start()])]
        source = "same"
        if not before:
            before = [v for _, v in _money_numbers(prev_text)] if prev_text else []
            source = "previous"
        if len(before) < 2 or (source == "previous" and len(before) > 6):
            continue  # un seul montant avant : « trois achats à 30 $ chacun, soit 90 $ » est une multiplication, pas une somme
        if re.match(r"\s*(?:%|percent|years?|months?|weeks?|days?|hours?|times)\b", text[m.end():]):
            continue
        claimed = _to_float(m.group(1))
        if claimed in before:
            continue
        if not _close(claimed, sum(before), 0.01):
            issues.append({"block": i, "kind": "sum", "claim": f"{' + '.join(f'{v:g}' for v in before)} = {claimed:g}",
                           "expected": round(sum(before), 2)})


def _check_formula(i: int, scene: dict, issues: list[dict]) -> None:
    terms = [str(t) for t in (scene.get("terms") or [])]
    if len(terms) < 3:
        return
    values: list[tuple[str, float]] = []
    for t in terms:
        m = re.match(r"\s*([=+\-−x*]?)\s*\$?(" + _NUM + ")", _normalize(t))
        if not m:
            return
        values.append((m.group(1), _to_float(m.group(2))))
    if values[-1][0] != "=" or values[0][0] not in ("",):
        return
    total = values[0][1]
    for op, v in values[1:-1]:
        if op in ("-", "−"):
            total -= v
        elif op == "+":
            total += v
        else:
            return
    if not _close(values[-1][1], total, 0.01):
        issues.append({"block": i, "kind": "formula", "claim": " ".join(terms), "expected": round(total, 2)})


def find_arithmetic_inconsistencies(blocks: list[dict]) -> list[dict]:
    """Relations arithmétiques reconnaissables et FAUSSES (jamais une relation non reconnue)."""
    issues: list[dict] = []
    texts = [_normalize(b.get("text", "")) for b in blocks]
    for i, text in enumerate(texts):
        _check_rate_pairs(i, text, issues)
        _check_goal(i, text, issues)
        _check_percent_of(i, text, issues)
        _check_chain(i, text, texts[i - 1] if i else "", issues)
        mg = blocks[i].get("motion_graphic")
        if isinstance(mg, dict) and (mg.get("sceneType") or mg.get("type")) == "formula":
            _check_formula(i, mg, issues)
    # apport cumulé annoncé (« 36 500 $ versés sur 20 ans ») cohérent avec UN apport annuel sans ambiguïté
    yearly = set()
    for text in texts:
        for r in _rates(text):
            yearly.add(round(r["amt"] * _UNIT_FACTOR_TO_YEAR[r["unit"]]))
    if yearly and (max(yearly) - min(yearly)) <= max(1, 0.03 * max(yearly)):
        per_year = sum(yearly) / len(yearly)
        for i, text in enumerate(texts):
            for sentence in _sentences(text):
                claim = _contribution_claim(sentence)
                if not claim:
                    continue
                total, n, unit = claim
                expected = per_year * (n if unit.startswith("year") else n / 12)
                if not _close(total, expected, 0.03):
                    issues.append({"block": i, "kind": "accumulation", "claim": f"{total:g} sur {n:g} {unit}", "expected": round(expected, 2)})
    return issues


# ---------------------------------------------------------------------------------------------
# Projections d'investissement : hypothèse explicite, jamais garanti
# ---------------------------------------------------------------------------------------------

_INVEST_CONTEXT = re.compile(r"\b(?:invest\w*|index fund|compound\w*|returns?|interest|stocks?|etf|portfolio|annual return)\b", re.IGNORECASE)
_PROJ_CUE = re.compile(
    r"\b(?:become|becomes|grow(?:s)? to|reach(?:es)?|worth|turns? into|end(?:s)? up (?:with|at)|could be|can grow|grows? into)\b", re.IGNORECASE
)
_HORIZON = re.compile(r"\b(?:in|after|over|by)\s+\d+\s+years?\b", re.IGNORECASE)
_BIG_AMOUNT = re.compile(r"\$?\d[\d,]{3,}")
_RATE_STATED = re.compile(r"\d+(?:\.\d+)?\s?(?:%|percent)", re.IGNORECASE)
_HEDGE = re.compile(r"\b(?:assum\w*|hypothetic\w*|example|suppose|imagine|if you|projected|projection|illustrat\w*|not guaranteed|estimate\w*|say you|say it)\b", re.IGNORECASE)
_GUARANTEE = re.compile(r"\b(?:guarantee[sd]?|risk[- ]free|can'?t lose|cannot lose|for sure|surefire|no risk|without risk)\b", re.IGNORECASE)
_NEGATED_GUARANTEE = re.compile(r"\b(?:not|no|never|n't|nothing|isn't|aren't|without a)\s+(?:\w+\s+){0,2}guarantee", re.IGNORECASE)


def find_projection_issues(blocks: list[dict]) -> list[dict]:
    texts = [_normalize(b.get("text", "")) for b in blocks]
    joined = " ".join(texts)
    out: list[dict] = []
    if _INVEST_CONTEXT.search(joined):
        for i, text in enumerate(texts):
            if not any(_PROJ_CUE.search(sn) and _HORIZON.search(sn) and _BIG_AMOUNT.search(sn) for sn in _sentences(text)):
                continue
            window = " ".join(texts[max(0, i - 1):i + 1])
            if not _RATE_STATED.search(window):
                out.append({"block": i, "kind": "rate_unstated"})
            elif not _HEDGE.search(window):
                out.append({"block": i, "kind": "unhedged"})
    for i, text in enumerate(texts):
        if _GUARANTEE.search(text) and not _NEGATED_GUARANTEE.search(text):
            out.append({"block": i, "kind": "guaranteed"})
    return out


# ---------------------------------------------------------------------------------------------
# Affirmations empiriques non sourcées
# ---------------------------------------------------------------------------------------------

_EMPIRICAL = (
    re.compile(r"\b(?:most|many|majority of|nearly all|almost all|a lot of)\s+(?:people|urges|impulses|cravings|buyers|shoppers|"
               r"consumers|investors|households|americans|folks|adults)\b", re.IGNORECASE),
    re.compile(r"\b(?:studies|research|surveys?|experts|scientists|data|statistics)\s+(?:show|shows|say|says|suggest|suggests|find|finds|"
               r"prove|proves|agree|confirm|confirms)\b", re.IGNORECASE),
    re.compile(r"\baccording to (?:studies|research|experts|a study|surveys?)\b", re.IGNORECASE),
    re.compile(r"\b\d{1,3}\s?(?:%|percent) of (?:people|americans|adults|households|buyers|shoppers|investors|consumers)\b", re.IGNORECASE),
    re.compile(r"\b(?:most|many) (?:urges|impulses|cravings)\b|\burges? (?:often )?(?:fade|disappear|pass|vanish)s? (?:by|within|after)\b", re.IGNORECASE),
    re.compile(r"\b(?:la plupart des (?:gens|personnes|français)|des études (?:montrent|prouvent)|selon (?:une|des) (?:étude|études))\b", re.IGNORECASE),
)


def find_unsupported_empirical_claims(script: dict) -> list[dict]:
    """Généralités chiffrées ou « les études montrent » sans source fournie (texte source / import)."""
    if script.get("source_type") == "pasted_text" or str(script.get("source_text") or "").strip():
        return []
    out = []
    for i, b in enumerate(script.get("blocks") or []):
        text = str(b.get("text") or "").replace("’", "'")
        for pattern in _EMPIRICAL:
            m = pattern.search(text)
            if m:
                out.append({"block": i, "phrase": m.group(0)})
                break
    return out


# ---------------------------------------------------------------------------------------------
# CTA qui promet quelque chose que le produit ne fournit pas
# ---------------------------------------------------------------------------------------------

_RESOURCE = r"(?:template|checklist|guide|plan|calculator|spreadsheet|script|ebook|cheat ?sheet|pdf|worksheet|modèle|tableur|calculateur)"
CTA_PROMISE_PATTERNS = (
    re.compile(r"\bcomment\s+[\"'“‘][^\"'”’]{1,24}[\"'”’]", re.IGNORECASE),
    re.compile(r"\bcomment\s+\w{1,12}\s+(?:below\s+)?(?:and|to)\s+(?:i|we)\b", re.IGNORECASE),
    re.compile(r"\b(?:dm|message|text)\s+me\b", re.IGNORECASE),
    re.compile(r"\bi(?:'ll| will)\s+(?:send|share|reply|dm|give|drop|email)\b", re.IGNORECASE),
    re.compile(r"\blink in (?:my |the )?bio\b", re.IGNORECASE),
    re.compile(rf"\b(?:want|need|get|grab)\s+(?:a|an|my|the|this|our|your)\s+[^?.!]{{0,40}}\b{_RESOURCE}\b", re.IGNORECASE),
    re.compile(rf"\bfree\s+{_RESOURCE}\b", re.IGNORECASE),
    re.compile(r"\bcommente\s+[\"'«“][^\"'»”]{1,24}[\"'»”]", re.IGNORECASE),
    re.compile(r"\b(?:écris|envoie)[- ]moi\b|\bje (?:t'|vous )?(?:envoie|partage|réponds|offre)\b|\blien en bio\b", re.IGNORECASE),
    re.compile(rf"\b(?:veux|veux-tu|voulez-vous)\s+(?:un|une|mon|le|la)\s+[^?.!]{{0,40}}\b{_RESOURCE}\b", re.IGNORECASE),
)


def has_cta_promise(text: str) -> bool:
    t = str(text or "").replace("’", "'")
    return any(p.search(t) for p in CTA_PROMISE_PATTERNS)


def find_cta_promises(blocks: list[dict]) -> list[int]:
    """Blocs CTA (rôle cta, ou dernier bloc) qui promettent une ressource, une réponse, un message ou une suite."""
    out = []
    last = len(blocks) - 1
    for i, b in enumerate(blocks):
        if (b.get("role") == "cta" or i == last) and has_cta_promise(b.get("text", "")):
            out.append(i)
    return out


# ---------------------------------------------------------------------------------------------
# Texte de remplissage visible
# ---------------------------------------------------------------------------------------------

_PLACEHOLDERS = (
    re.compile(r"\$[A-Za-z]"), re.compile(r"\b[XN]\s*%"), re.compile(r"\b(?:placeholder|lorem ipsum|tbd)\b", re.I),
    re.compile(r"\[[^\]]*\]|\{[^}]*\}"), re.compile(r"^\s*(?:an?\s+)?(?:example|sample)(?:\s+(?:rate|value|total|amount|number))?\s*$", re.I),
)


def find_placeholders(strings_by_block: list[list[str]]) -> list[int]:
    return [i for i, strings in enumerate(strings_by_block) if any(any(p.search(s) for p in _PLACEHOLDERS) for s in strings if s)]
