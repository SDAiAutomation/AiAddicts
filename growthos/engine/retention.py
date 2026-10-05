"""Retention & Virality Engine V1 — architecture éditoriale short-form.

STOP -> HOLD -> PROGRESS -> REWARD -> RETURN :

- STOP     : gagner les premières secondes (hook)
- HOLD     : maintenir la curiosité (boucle ouverte)
- PROGRESS : chaque bloc apporte une information nouvelle
- REWARD   : tenir la promesse du hook (payoff)
- RETURN   : une raison de revoir une vidéo Faceloop (CTA / série)

Ce module NE PRÉDIT PAS la viralité : aucun score de viralité, aucune
probabilité. Il décrit des caractéristiques CONTRÔLABLES d'un script (hook,
rythme, boucle ouverte, payoff, répétitions, progression visuelle, CTA) sous
forme de diagnostics factuels et actionnables.

Tout est déterministe : aucun appel IA, aucun réseau, aucun embedding. Le
module ne coûte donc ni appel LLM par bloc, ni appel image, ni fournisseur
payant. Il tourne sur le script déjà généré par l'appel LLM existant (le
`contentStrategy` est produit dans CE même appel, voir RETENTION_ENGINE.md).

Tout est optionnel et rétrocompatible : un script sans `contentStrategy`, sans
`retentionRole` ni `informationGain` (tous les scripts antérieurs) est analysé
avec les seuls signaux déductibles du texte, et `validate_*` ne rejette que
des valeurs présentes mais invalides.

Conventions : les indices de blocs stockés (`openedAtBlock`, ...) sont à base 0
(le hook est le bloc 0) ; les messages affichés sont à base 1 ("bloc 4").
Les messages sont en français, comme `quality_flags` ; chaque problème porte
aussi un `code` stable pour une éventuelle localisation côté interface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import integrity

VERSION = "retention:v3"

# Défauts qu'un spectateur verrait (ou qui seraient une information fausse / une promesse non tenue) : le
# contrôle qualité du moteur retient la vidéo en `quality_check` au lieu de la laisser partir en publication.
BLOCKING_CODES = frozenset((
    "arithmetic_inconsistency", "projection_assumption_missing", "guaranteed_language", "role_label_leak",
    "viewer_placeholder", "unsupported_cta_promise",
))

HOOK_TYPES = (
    "contradiction", "curiosity_gap", "specific_number", "warning", "scenario",
    "comparison", "unexpected_fact", "mistake", "challenge", "transformation",
)
RETENTION_ROLES = (
    "hook", "setup", "escalation", "evidence", "pattern_interrupt", "reveal", "payoff", "cta",
)
INFORMATION_GAINS = (
    "new_fact", "new_example", "new_consequence", "new_visual_evidence",
    "new_question", "answer", "cta",
)
CTA_INTENTS = (
    "none", "follow_for_series", "question", "next_episode", "save", "share", "subscribe",
)
STRATEGY_TEXT_FIELDS = (
    "audiencePromise", "coreQuestion", "viewerProblem", "payoff",
    "hookText", "curiosityMechanism", "emotionalDriver",
)

# Champs observables d'une future boucle d'apprentissage (PAS implémentée ici :
# ni API YouTube, ni ML). `views` et `engagedViews` restent DISTINCTS :
# YouTube a changé le comptage des vues Shorts en 2025.
OBSERVED_METRIC_FIELDS = (
    "shownInFeed", "choseToView", "swipedAway", "views", "engagedViews",
    "averageViewDuration", "averagePercentageViewed", "likes", "comments",
    "shares", "subscribersGained",
)

# visualPurpose (engine/shot_planning.py) -> rôle de rétention. `explain` n'est
# volontairement PAS mappé : c'est l'étiquette « explication générique » dont
# on veut justement repérer les suites (HOOK / EXPLICATION x N / CTA).
_PURPOSE_TO_ROLE = {
    "hook": "hook", "establish": "setup", "action": "escalation",
    "evidence": "evidence", "reaction": "pattern_interrupt",
    "reveal": "reveal", "payoff": "payoff", "cta": "cta",
}

# Débit de la voix off (mots/min) — mesuré en production, miroir de
# growthos-web `src/lib/script-length.ts` (fr 213, en 172, défaut prudent).
WORDS_PER_MINUTE = {"fr": 213, "en": 172}
DEFAULT_WORDS_PER_MINUTE = 195


@dataclass(frozen=True)
class RetentionConfig:
    """Seuils CONFIGURABLES. Aucun seuil de « succès » universel : les valeurs
    par défaut reprennent des contraintes déjà présentes dans le projet
    (hook <= 4 s : engine/quality.py ; CTA <= 12 mots : editorial_quality.py)
    ou des bornes de lisibilité du texte. `None` = mesure descriptive, jamais
    signalée."""
    hook_max_words: int = 14
    hook_delayed_value_words: int = 8
    hook_max_sec: float = 4.0
    cta_max_words: int = 12
    same_structure_run: int = 3
    explanation_run: int = 3
    number_slide_run: int = 3
    repetition_min_tokens: int = 4
    repetition_novel_ratio: float = 0.25
    near_duplicate_jaccard: float = 0.6
    max_block_sec: float | None = None
    max_seconds_before_payoff: float | None = None
    max_seconds_before_first_example: float | None = None
    words_per_minute: dict = field(default_factory=lambda: dict(WORDS_PER_MINUTE))
    default_words_per_minute: int = DEFAULT_WORDS_PER_MINUTE


DEFAULT_CONFIG = RetentionConfig()

# --------------------------------------------------------------------------
# Texte : tokens, mots vides, motifs multilingues
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\d[\d.,]*|[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")

_STOPWORDS = frozenset((
    # en
    "the a an and or but of to in on at for with from by as is are was were be been being it its this that these "
    "those you your yours we our they their he she his her i me my not no do does did doing have has had will "
    "would can could should just so than then there here what when where which who why how if about into over "
    "out up down off more most some any all each very too also only still even own same such "
    # fr
    "le la les un une des du de et ou mais donc or ni car que qui quoi dont où ce cet cette ces se sa son ses "
    "ta ton tes ma mon mes tu te toi il elle on nous vous ils elles lui leur leurs je me moi ne pas plus en y "
    "est sont était être été avoir a ont avait fait fais faire dans sur sous avec sans pour par au aux si comme "
    "tout tous toute toutes très aussi encore déjà puis alors "
    # es / de / it / pt (listes courtes : analyse indicative, voir RETENTION_ENGINE.md)
    "el los las un una unos unas y o pero que de del al en con sin por para es son se lo su sus "
    "der die das ein eine und oder aber nicht ist sind mit von zu im den dem des auf für "
    "il lo gli e o ma che di del della con per non è sono si "
    "os as um uma e ou mas que de do da em com sem para não é são"
).split())

_GENERIC_OPENINGS = (
    # en
    "did you know", "have you ever wondered", "have you ever", "in today's video", "in this video",
    "today we", "today i", "let's talk about", "lets talk about", "let's dive", "managing money can",
    "here are", "here's a few", "here is a few", "welcome", "hey guys", "hi everyone", "hello",
    "you won't believe", "are you ready",
    # fr
    "saviez-vous", "le savais-tu", "tu savais", "vous savez", "dans cette vidéo", "aujourd'hui",
    "parlons de", "voici quelques", "bienvenue", "bonjour", "tu veux savoir", "vous voulez savoir",
    "tu as déjà", "vous avez déjà",
    # es / de / it / pt
    "¿sabías que", "sabías que", "en este vídeo", "en este video", "hoy vamos", "hablemos de", "hola",
    "wusstest du", "in diesem video", "heute sprechen", "hallo",
    "sapevi che", "in questo video", "oggi parliamo", "ciao",
    "você sabia", "voce sabia", "neste vídeo", "hoje vamos", "olá",
)

_CONTRAST_MARKERS = (
    "but", "yet", "still", "until", "instead", "only", "even though", "despite", "so why", "why",
    "mais", "pourtant", "malgré", "alors pourquoi", "pourquoi", "sauf", "encore", "seulement",
    "pero", "aber", "ma", "porém", "porque",
)
_WARNING_MARKERS = (
    "never", "don't", "dont", "do not", "stop", "avoid", "careful", "warning", "mistake", "wrong",
    "jamais", "ne fais pas", "ne faites pas", "arrête", "arrete", "évite", "evite", "attention", "erreur",
    "nunca", "nie ", "mai ",
)
_CURIOSITY_MARKERS = (
    "why", "how", "secret", "what happens", "nobody", "no one", "the one thing", "hidden", "truth",
    "pourquoi", "comment", "personne", "ce que", "vérité", "verite", "caché", "cache",
)

_TYPE_SIGNALS = {
    "contradiction": ("but", "yet", "still", "so why", "even though", "despite", "mais", "pourtant",
                      "malgré", "alors pourquoi", "encore", "?"),
    "curiosity_gap": _CURIOSITY_MARKERS + ("?",),
    "specific_number": (),  # un chiffre (voir _type_signal)
    "warning": _WARNING_MARKERS,
    "scenario": ("you wake", "imagine", "what if", "you're", "you are", "you have", "you just", "if you",
                 "suppose", "si tu", "si vous", "tu te réveilles", "tu as", "vous avez", "tu es"),
    "comparison": (" vs", "versus", "than", "same", "two ", "both", "while", "only one", "deux", "même",
                   "meme", "contre", "tandis", "alors que"),
    "unexpected_fact": ("actually", "turns out", "in fact", "surprising", "en réalité", "en realite",
                        "en fait", "pourtant"),
    "mistake": ("mistake", "wrong", "error", "fail", "worst", "biggest", "erreur", "faute", "pire"),
    "challenge": ("challenge", "can you", "try", "dare", "bet", "défi", "defi", "essaie", "essayez", "peux-tu"),
    "transformation": ("from ", "before", "after", "turn", "becomes", "become", "into", "transform", "avant",
                       "après", "apres", "devient", "passer", "→"),
}

_PROMISE_CUES = (
    "at the end", "stay until", "stay till", "wait for it", "i'll show you", "i will show you",
    "let me show you", "here's why", "here is why", "here's how", "here is how", "you'll see why",
    "à la fin", "reste jusqu", "restez jusqu", "je vais te montrer", "je vais vous montrer",
    "voici pourquoi", "voici comment", "tu vas voir", "vous allez voir",
)
_GENERIC_ADVICE = (
    "consistency matters", "stay consistent", "be consistent", "start today", "just start", "the key is consistency",
    "la régularité compte", "reste régulier", "commence aujourd'hui",
    "be smarter", "be more careful", "be careful with money", "just save more", "manage your money",
    "stay disciplined", "be responsible", "spend wisely", "make better choices", "think before you spend",
    "sois plus malin", "soyez plus malin", "sois plus prudent", "gère mieux", "gérez mieux",
    "sois discipliné", "dépense intelligemment", "fais les bons choix",
)
_CTA_BOILERPLATE = (
    "like and subscribe", "smash the like", "smash that", "don't forget to subscribe", "hit the bell",
    "likez", "aime la vidéo", "aimez la vidéo", "abonne-toi", "abonnez-vous", "n'oublie pas de t'abonner",
)
_CTA_PATTERNS = {
    "subscribe": ("subscribe", "abonne", "suscríbete", "abonniere", "iscriviti", "inscreva"),
    "follow_for_series": ("follow", "suis", "suivez", "sigue", "folge", "segui", "siga"),
    "next_episode": ("next episode", "next rule", "is next", "part 2", "épisode suivant", "prochain",
                     "la suite", "next time"),
    "save": ("save this", "save it", "bookmark", "enregistre", "sauvegarde", "garde ça"),
    "share": ("share this", "share it", "send this", "tag a friend", "partage", "envoie ça", "envoie-le"),
}

# --------------------------------------------------------------------------
# Rôles de rétention -> scènes Motion Graphics recommandées (progression visuelle)
# --------------------------------------------------------------------------

# Scènes qui conviennent à chaque rôle (voir engine/motion_graphics/schema.py).
ROLE_SCENE_FIT: dict[str, tuple[str, ...]] = {
    "hook": ("big_number", "comparison", "before_after", "warning", "money_split"),
    "setup": ("icon_text", "timeline", "money_split", "progress_bar"),
    "escalation": ("progress_bar", "compound_growth", "bar_chart", "timeline", "donut_chart"),
    "evidence": ("big_number", "bar_chart", "comparison", "donut_chart", "money_split", "function_graph"),
    "pattern_interrupt": ("warning", "comparison", "before_after", "big_number"),
    "reveal": ("before_after", "formula", "equation_steps", "function_graph", "big_number", "compound_growth"),
    "payoff": ("formula", "equation_steps", "big_number", "before_after", "checklist"),
    "cta": ("icon_text", "checklist"),
}
ROLE_VISUAL_INTENT = {
    "hook": "contraste, chiffre ou transformation le plus fort",
    "setup": "établir le contexte",
    "escalation": "compteur progressif / graphique qui évolue / objets qui s'accumulent",
    "evidence": "chiffre concret ou comparaison",
    "pattern_interrupt": "changement de composition ou accent typographique",
    "reveal": "transformation visuelle",
    "payoff": "état final simplifié",
    "cta": "minimal, propre, sans distraction",
}
_HEAVY_SCENES = ("bar_chart", "donut_chart", "compound_growth", "money_split", "timeline")
_WEAK_HOOK_SCENES = ("icon_text", "checklist", "formula")
_NUMERIC_SCENES = ("big_number",)
_ALTERNATIVE_SHOTS = ("close_up", "wide", "insert", "medium", "pov")


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"thousand": 1_000, "million": 1_000_000}
_NUMBER_WORDS = frozenset(_UNITS) | frozenset(_TENS) | frozenset(_SCALES) | {"hundred"}
_WORD_RE = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")


def _number_value(words: list[str]) -> int:
    total = current = 0
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        else:  # thousand / million
            total += (current or 1) * _SCALES[w]
            current = 0
    return total + current


def normalize_number_words(text: str) -> str:
    """« five dollars » -> « 5 dollars », « ten thousand » -> « 10000 », « twenty-six thousand » -> « 26000 ».

    Volontairement étroit (anglais, entiers jusqu'au million) : seulement ce dont les diagnostics
    ont besoin pour comparer « five dollars » à « $5 ». Un « one » isolé (« only one becomes
    wealthy ») n'est PAS converti : c'est un pronom autant qu'un nombre."""
    text = str(text or "")
    pieces: list[str] = []
    last = 0
    run: list[tuple[int, int, str]] = []  # (start, end, word)

    def flush() -> None:
        nonlocal last
        if not run:
            return
        words = [w for _, _, w in run]
        if not (len(words) == 1 and words[0] == "one"):
            pieces.append(text[last:run[0][0]])
            pieces.append(str(_number_value(words)))
            last = run[-1][1]
        run.clear()

    for m in _WORD_RE.finditer(text):
        parts = m.group(0).lower().split("-")
        if all(part in _NUMBER_WORDS for part in parts):
            gap = text[run[-1][1]:m.start()] if run else ""
            if run and gap.strip().lower() not in ("", "and"):
                flush()
            run.extend((m.start(), m.end(), part) for part in parts)
        elif run and m.group(0).lower() == "and" and re.match(r"\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\b", text[m.end():], re.I):
            continue
        else:
            flush()
    flush()
    pieces.append(text[last:])
    return "".join(pieces)


def _has_number(text: str) -> bool:
    return bool(re.search(r"\d", normalize_number_words(text)))


_K_SUFFIX = re.compile(r"(\d+(?:\.\d+)?)k(?![A-Za-z])", re.IGNORECASE)


def _expand_k(text: str) -> str:
    """« $25k » -> « $25000 » (notation courante des montants dits à l'oral : « vingt-cinq mille »)."""
    return _K_SUFFIX.sub(lambda m: str(round(float(m.group(1)) * 1000)), text)


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN_RE.findall(_expand_k(normalize_number_words(str(text or ""))).lower().replace("’", "'")):
        if "'" in raw:
            head, _, tail = raw.partition("'")
            if len(head) <= 2 and tail:  # élision (l'épargne, d'augmentation, qu'il) : garder le mot
                raw = tail
        if raw[0].isdigit():
            raw = raw.rstrip(".,")
            if _THOUSANDS_RE.match(raw):
                raw = re.sub(r"[.,]", "", raw)
        out.append(raw)
    return out


def _words(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").strip())


def _norm(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token[0].isdigit() else token


def _content_tokens(text: str) -> list[str]:
    return [
        _norm(t) for t in _tokens(text)
        if t[0].isdigit() or (len(t) > 2 and t not in _STOPWORDS)
    ]


def _numbers(text: str) -> set[str]:
    return {t for t in _tokens(text) if t[0].isdigit()}


def _number_present(number: str, candidates: set[str], tolerance: float = 0.05) -> bool:
    """`number` est dit dans le script, à l'arrondi près (±5 %) : « 364307 » annoncé ~ « 364000 » dit."""
    if number in candidates:
        return True
    try:
        target = float(number)
    except ValueError:
        return False
    for c in candidates:
        try:
            value = float(c)
        except ValueError:
            continue
        if target and abs(value - target) / abs(target) <= tolerance:
            return True
    return False


def _contains_any(text: str, needles) -> str | None:
    low = " " + str(text or "").lower().replace("’", "'") + " "
    return next((n for n in needles if n in low), None)


# Étiquettes internes de rétention : des MÉTADONNÉES, jamais du texte lu ou affiché. Garde volontairement
# étroite (une étiquette en début de phrase suivie d'une ponctuation de libellé) : « Evidence, not hope, wins »
# ou « Reveal your spending » restent légitimes. Miroir de growthos-web src/lib/retention-contract.ts.
ROLE_LABEL_RE = re.compile(
    r"(?:^|[.!?]\s+)\W*(?:(?:(?:concrete|practical|real|final|big|main|actual|key|true)\s+)?"
    r"(?:pattern[ _-]?interrupt|reveal|resolution|escalation|payoff|cta|open[ _-]?loop|relance|answer first)"
    r"\s*[,:;.\u2014\u2013-]|(?:evidence|setup|set[ _-]up)\s*[:.\u2014\u2013-])\s*\w",
    re.IGNORECASE,
)
_BARE_ROLE_LABELS = frozenset(
    ("pattern interrupt", "reveal", "resolution", "escalation", "payoff", "cta", "open loop", "relance", "setup", "evidence")
)
_VIEWER_TEXT_KEYS = ("title", "label", "displayValue", "displayText", "text", "emphasis")
_VIEWER_LIST_KEYS = ("steps", "items", "terms")

# Expérience à la première personne présentée comme vécue. Conservateur : verbes d'expérience au passé /
# parfait, jamais « I'll show you » ni une explication à la première personne.
_FIRST_PERSON_RE = re.compile(
    r"\bI(?:'ve| have)? (?:opened|invested|saved|spent|paid|bought|used|tried|started|stopped|counted|handed|put|lost|"
    r"earned|borrowed|checked|watched|asked|learned|realized|decided|found|felt|made|kept|set up)\b"
    r"|\bwhen I (?:was|had|got|first)\b|\bj['’]ai (?:ouvert|investi|épargné|dépensé|acheté|payé|essayé|commencé|"
    r"arrêté|compté|perdu|gagné|emprunté|appris|compris|décidé|trouvé)\b",
    re.IGNORECASE,
)


def _viewer_strings(block: dict) -> list[str]:
    out = [str(block.get("text") or "")]
    mg = block.get("motion_graphic")
    if isinstance(mg, dict):
        for key in _VIEWER_TEXT_KEYS:
            if isinstance(mg.get(key), str):
                out.append(mg[key])
        for key in _VIEWER_LIST_KEYS:
            if isinstance(mg.get(key), list):
                for value in mg[key]:
                    if isinstance(value, dict):
                        out.extend(str(value.get(name) or "") for name in ("equation", "explanation"))
                    else:
                        out.append(str(value))
        for row in mg.get("data") or []:
            if isinstance(row, dict):
                out.extend(str(row.get(k) or "") for k in ("label", "displayValue"))
        for key in ("optionA", "optionB", "before", "after"):
            if isinstance(mg.get(key), dict):
                out.extend(str(mg[key].get(k) or "") for k in ("label", "displayValue"))
    return out


def find_role_label_leaks(blocks: list[dict]) -> list[int]:
    """Indices (base 0) des blocs dont un texte lu ou affiché contient une étiquette interne."""
    leaks = []
    for i, block in enumerate(blocks):
        for text in _viewer_strings(block):
            if ROLE_LABEL_RE.search(text) or text.strip().strip(".:,;-").lower() in _BARE_ROLE_LABELS:
                leaks.append(i)
                break
    return leaks


def find_first_person_anecdotes(blocks: list[dict]) -> list[int]:
    return [i for i, b in enumerate(blocks) if _FIRST_PERSON_RE.search(str(b.get("text") or "").replace("’", "'"))]


def _issue(code: str, message: str, blocks: list[int] | None = None, severity: str = "info") -> dict:
    out = {"code": code, "severity": severity, "message": message}
    if blocks:
        out["blocks"] = list(blocks)
    return out


def _pretty(indices: list[int]) -> str:
    return "/".join(str(i + 1) for i in indices)


def _body_blocks(script: dict) -> list[dict]:
    return [b for b in (script.get("blocks") or []) if isinstance(b, dict)]


def _hook_index(blocks: list[dict]) -> int | None:
    for i, b in enumerate(blocks):
        if b.get("role") == "hook":
            return i
    return 0 if blocks else None


def _cta_index(blocks: list[dict]) -> int | None:
    for i in range(len(blocks) - 1, -1, -1):
        if blocks[i].get("role") == "cta":
            return i
    return None


def _strategy_target(script: dict | None) -> float | None:
    value = (script or {}).get("contentStrategy", {}) if isinstance((script or {}).get("contentStrategy"), dict) else {}
    target = value.get("targetDurationSec")
    return float(target) if isinstance(target, (int, float)) and not isinstance(target, bool) else None


def _strategy(script: dict) -> dict:
    cs = script.get("contentStrategy")
    return cs if isinstance(cs, dict) else {}


# --------------------------------------------------------------------------
# Validation du contrat (appelée par engine/script.validate_script)
# --------------------------------------------------------------------------

def validate_content_strategy(cs) -> None:
    """`contentStrategy` (optionnel) : objet dont chaque champ est optionnel
    mais, s'il est présent, doit être valide. Ne rejette jamais l'absence."""
    if cs is None:
        return
    if not isinstance(cs, dict):
        raise ValueError("'contentStrategy' doit être un objet (ou absent)")
    for name in STRATEGY_TEXT_FIELDS:
        value = cs.get(name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"contentStrategy.{name} doit être une chaîne")
    hook_type = cs.get("hookType")
    if hook_type is not None and hook_type not in HOOK_TYPES:
        raise ValueError(f"contentStrategy.hookType invalide : '{hook_type}' (attendu : {list(HOOK_TYPES)})")
    cta_intent = cs.get("ctaIntent")
    if cta_intent is not None and cta_intent not in CTA_INTENTS:
        raise ValueError(f"contentStrategy.ctaIntent invalide : '{cta_intent}' (attendu : {list(CTA_INTENTS)})")
    duration = cs.get("targetDurationSec")
    if duration is not None and (
        isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0
    ):
        raise ValueError("contentStrategy.targetDurationSec doit être un nombre > 0")


def validate_series(series) -> None:
    """`series` (optionnel) : {name, episode, continuityCTA}. Jamais imposé."""
    if series is None:
        return
    if not isinstance(series, dict):
        raise ValueError("'series' doit être un objet (ou absent)")
    name = series.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("series.name est requis (chaîne non vide)")
    episode = series.get("episode")
    if episode is not None and (isinstance(episode, bool) or not isinstance(episode, int) or episode < 1):
        raise ValueError("series.episode doit être un entier >= 1")
    cta = series.get("continuityCTA")
    if cta is not None and not isinstance(cta, str):
        raise ValueError("series.continuityCTA doit être une chaîne")


def normalize_open_loops(script: dict) -> list[dict]:
    """`openLoops` (liste) ou `openLoop` (objet unique, forme conceptuelle du
    cahier des charges) -> liste normalisée. Absent -> []."""
    loops = script.get("openLoops")
    if loops is None and script.get("openLoop") is not None:
        loops = [script["openLoop"]]
    return [loop for loop in (loops or []) if isinstance(loop, dict)]


def validate_open_loops(script: dict, n_blocks: int) -> None:
    raw = script.get("openLoops")
    if raw is None and script.get("openLoop") is not None:
        raw = [script["openLoop"]]
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ValueError("'openLoops' doit être une liste (ou absent)")
    for i, loop in enumerate(raw):
        if not isinstance(loop, dict):
            raise ValueError(f"openLoops[{i}] doit être un objet")
        question = loop.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"openLoops[{i}] : 'question' manquante ou vide")
        for key in ("openedAtBlock", "resolvedAtBlock"):
            value = loop.get(key)
            if value is None and key == "resolvedAtBlock":
                continue  # boucle non résolue : signalée par l'analyse, pas rejetée
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < n_blocks:
                raise ValueError(f"openLoops[{i}].{key} doit être un indice de bloc (0..{n_blocks - 1})")


def validate_block_retention(block: dict, index: int) -> None:
    """Champs de bloc optionnels `retentionRole` / `informationGain`."""
    role = block.get("retentionRole")
    if role is not None and role not in RETENTION_ROLES:
        raise ValueError(f"blocks[{index}] : 'retentionRole' invalide : '{role}' (attendu : {list(RETENTION_ROLES)})")
    gain = block.get("informationGain")
    if gain is not None and gain not in INFORMATION_GAINS:
        raise ValueError(
            f"blocks[{index}] : 'informationGain' invalide : '{gain}' (attendu : {list(INFORMATION_GAINS)})"
        )


def validate_retention_fields(script: dict, n_blocks: int) -> None:
    validate_content_strategy(script.get("contentStrategy"))
    validate_series(script.get("series"))
    validate_open_loops(script, n_blocks)


# --------------------------------------------------------------------------
# 1. Hook
# --------------------------------------------------------------------------

def _type_signal(hook_type: str, text: str) -> bool:
    if hook_type == "specific_number":
        return bool(re.search(r"\d", text))
    if hook_type == "unexpected_fact" and re.search(r"\d", text):
        return True
    markers = _TYPE_SIGNALS.get(hook_type, ())
    low = " " + text.lower().replace("’", "'") + " "
    return any(m in low for m in markers)


def diagnose_hook(
    text: str,
    hook_type: str | None = None,
    title: str | None = None,
    config: RetentionConfig = DEFAULT_CONFIG,
) -> dict:
    """Diagnostic DÉTERMINISTE d'un hook (aucun appel IA, aucune probabilité)."""
    text = str(text or "").strip()
    words = _words(text)
    low = text.lower().replace("’", "'")
    stripped = low.lstrip("¿¡\"'« ")
    generic = next((p for p in _GENERIC_OPENINGS if stripped.startswith(p)), None)
    has_number = _has_number(text)
    content = _content_tokens(text)
    tension_marker = _contains_any(text, _CONTRAST_MARKERS + _WARNING_MARKERS + _CURIOSITY_MARKERS)
    tension = "?" in text or tension_marker is not None

    # Indice du premier mot « porteur de valeur » : un chiffre ou un marqueur
    # de tension. Plus il est tardif, plus le sujet arrive tard.
    first_value: int | None = None
    markers = [m.strip() for m in _CONTRAST_MARKERS + _WARNING_MARKERS + _CURIOSITY_MARKERS if " " not in m.strip()]
    for i, word in enumerate(w.lower().replace("’", "'") for w in words):
        if word[0].isdigit() or any(part in markers for part in word.split("'")) or any(
            part in _NUMBER_WORDS and part != "one" for part in word.split("-")
        ):
            first_value = i
            break
    if first_value is None and "?" in text:
        first_value = max(0, len(words) - 1)
    # Un hook court n'a pas de « valeur tardive » : la règle ne vaut qu'au-delà d'une dizaine de mots.
    delayed = len(words) > 10 and (first_value is None or first_value > config.hook_delayed_value_words)

    repeats_title = False
    if title:
        title_set, hook_set = set(_content_tokens(title)), set(content)
        repeats_title = bool(hook_set) and hook_set <= title_set

    issues: list[dict] = []
    if not text:
        issues.append(_issue("hook_missing", "Aucun hook explicite.", severity="high"))
    else:
        if generic:
            issues.append(_issue("generic_opening", f"Ouverture générique (« {generic} »).", severity="high"))
        if len(words) > config.hook_max_words:
            issues.append(_issue(
                "hook_too_long", f"Hook de {len(words)} mots (configuré : {config.hook_max_words} maximum).",
            ))
        if len(content) < 2 and not has_number:
            issues.append(_issue("no_concrete_subject", "Hook sans sujet concret identifiable."))
        if delayed and (tension or has_number):
            issues.append(_issue(
                "delayed_value",
                f"La valeur du hook n'apparaît qu'au mot {first_value + 1}." if first_value is not None
                else "La valeur du hook arrive tard.",
            ))
        if repeats_title:
            issues.append(_issue("repeats_title", "Le hook répète le titre sans rien ajouter."))

    # Le type de hook est une métadonnée d'ANALYSE : un hook efficace peut ne ressembler à aucune catégorie,
    # et la liste de mots-clés est trop pauvre pour juger. Signal rapporté (`hookTypeSignal`), jamais un défaut.
    type_signal = _type_signal(hook_type, text) if hook_type and text else None

    return {
        "text": text,
        "hookType": hook_type,
        "wordCount": len(words),
        "genericOpening": generic is not None,
        "containsSpecificNumber": has_number,
        "tensionDetected": tension,
        "delayedValue": bool(text) and delayed,
        "firstValueWord": (first_value + 1) if first_value is not None else None,
        "repeatsTitle": repeats_title,
        "hookTypeSignal": type_signal,
        "issues": issues,
    }


# --------------------------------------------------------------------------
# 2. Rôles de rétention
# --------------------------------------------------------------------------

def assign_retention_roles(blocks: list[dict]) -> list[dict]:
    """Un rôle de rétention par bloc : déclaré (`retentionRole`) > rôle du
    script (hook/cta) > déduit de `visualPurpose` > `None`."""
    out = []
    for b in blocks:
        declared = b.get("retentionRole")
        if declared in RETENTION_ROLES:
            out.append({"role": declared, "source": "declared"})
        elif b.get("role") in ("hook", "cta"):
            out.append({"role": b["role"], "source": "script_role"})
        elif _PURPOSE_TO_ROLE.get(b.get("visualPurpose")) in RETENTION_ROLES:
            out.append({"role": _PURPOSE_TO_ROLE[b["visualPurpose"]], "source": "visualPurpose"})
        else:
            out.append({"role": None, "source": "unassigned"})
    return out


def analyze_structure(blocks: list[dict], roles: list[dict], config: RetentionConfig) -> dict:
    """Progression narrative. `available: False` quand aucun bloc du corps ne
    porte d'information de rôle (scripts anciens) : aucun problème de
    structure n'est alors inventé."""
    sequence = [r["role"] for r in roles]
    body = [(i, r["role"]) for i, r in enumerate(roles) if blocks[i].get("role") not in ("hook", "cta")]
    informative = any(role for _, role in body)
    result = {
        "available": informative,
        "sequence": [s or "unassigned" for s in sequence],
        "issues": [],
    }
    if not informative:
        return result
    issues = result["issues"]

    # Suite de blocs « explication » (rôle absent, ou `setup` répété) : le
    # schéma HOOK / EXPLICATION x N / CTA que l'architecture veut éviter.
    run: list[int] = []
    for i, role in body + [(-1, "__end__")]:
        if role in (None, "setup") and i != -1:
            run.append(i)
            continue
        if len(run) >= config.explanation_run:
            issues.append(_issue(
                "explanation_run",
                f"Blocs {_pretty(run)} : {len(run)} blocs d'explication consécutifs sans rôle de progression déclaré.",
                run,
            ))
        run = []

    # Pas de séquence obligatoire : les rôles sont des outils. Ni « il manque une révélation », ni
    # « escalade absente », ni « mise en contexte tardive » : ces règles supposaient un modèle à remplir.
    return result


# --------------------------------------------------------------------------
# 3. Progression d'information / répétitions
# --------------------------------------------------------------------------

def analyze_repetition(blocks: list[dict], config: RetentionConfig) -> dict:
    roles = assign_retention_roles(blocks)
    seen: set[str] = set()
    seen_numbers: set[str] = set()
    per_block: list[dict] = []
    issues: list[dict] = []
    token_sets: list[set[str]] = []
    for i, b in enumerate(blocks):
        toks = set(_content_tokens(b.get("text", "")))
        nums = _numbers(b.get("text", ""))
        token_sets.append(toks)
        novel = toks - seen
        ratio = (len(novel) / len(toks)) if toks else 1.0
        new_numbers = sorted(nums - seen_numbers)
        entry = {
            "block": i, "declaredGain": b.get("informationGain"),
            "novelTokenRatio": round(ratio, 2), "newNumbers": new_numbers,
        }
        per_block.append(entry)
        skip = i == 0 or b.get("role") == "cta"
        # Une révélation / un payoff / une réponse déclarée recombine
        # légitimement des termes déjà posés (« 1 000 - 850 = 150 ») : le
        # recouvrement lexical n'y prouve pas une redite.
        synthesizes = roles[i]["role"] in ("reveal", "payoff") or b.get("informationGain") == "answer"
        repeats = (
            not skip and not synthesizes and len(toks) >= config.repetition_min_tokens
            and ratio <= config.repetition_novel_ratio and not new_numbers
        )
        if repeats:
            issues.append(_issue(
                "repeats_earlier", f"Bloc {i + 1} : n'apporte presque rien de nouveau (idées déjà énoncées).",
                [i], severity="high",
            ))
        # Doublon proche d'un des 3 blocs précédents.
        for j in range(max(0, i - 3), i):
            union = toks | token_sets[j]
            if (
                not skip and len(toks) >= config.repetition_min_tokens and len(token_sets[j]) >= config.repetition_min_tokens
                and union and len(toks & token_sets[j]) / len(union) >= config.near_duplicate_jaccard
            ):
                issues.append(_issue(
                    "near_duplicate", f"Blocs {_pretty([j, i])} : formulations quasi identiques.", [j, i], severity="high",
                ))
                break
        seen |= toks
        seen_numbers |= nums
    declared = sum(1 for b in blocks if b.get("informationGain"))
    return {"perBlock": per_block, "declaredGainCount": declared, "issues": issues}


# --------------------------------------------------------------------------
# 4. Rythme
# --------------------------------------------------------------------------

def _block_seconds(blocks, durations, language, config) -> tuple[list[float], str]:
    if durations and len(durations) == len(blocks):
        return [float(d) for d in durations], "measured"
    wpm = config.words_per_minute.get(language or "", config.default_words_per_minute)
    return [len(_words(b.get("text", ""))) / wpm * 60.0 for b in blocks], "estimated"


def find_payoff_index(blocks: list[dict], roles: list[dict]) -> tuple[int | None, str]:
    for i, r in enumerate(roles):
        if r["role"] == "payoff" and blocks[i].get("role") != "cta":
            return i, "role"
    reveal = [i for i, r in enumerate(roles) if r["role"] == "reveal" and blocks[i].get("role") != "cta"]
    if reveal:
        return reveal[-1], "reveal"
    cta = _cta_index(blocks)
    last = (cta - 1) if cta is not None else len(blocks) - 1
    hook = _hook_index(blocks)
    if last >= 0 and last != hook:
        return last, "last_body_block"
    if cta is not None:
        return cta, "cta_only"  # le CTA est le seul contenu après le hook : signalé par analyze_payoff
    return None, "none"


def analyze_pacing(blocks, roles, durations, language, config, payoff_index, script=None) -> dict:
    secs, source = _block_seconds(blocks, durations, language, config)
    starts = []
    t = 0.0
    for s in secs:
        starts.append(t)
        t += s
    words_per_block = [len(_words(b.get("text", ""))) for b in blocks]
    hook_i = _hook_index(blocks)
    cta_i = _cta_index(blocks)
    longest = max(range(len(secs)), key=lambda i: secs[i]) if secs else None

    first_example = None
    for i, b in enumerate(blocks):
        if i == hook_i or i == cta_i:
            continue
        if _has_number(b.get("text", "")) or b.get("informationGain") in ("new_example", "new_visual_evidence"):
            first_example = i
            break

    pacing = {
        "durationSource": source,
        "totalSec": round(t, 1),
        "wordsPerBlock": {
            "min": min(words_per_block, default=0), "max": max(words_per_block, default=0),
            "avg": round(sum(words_per_block) / len(words_per_block), 1) if words_per_block else 0,
        },
        "hookSec": round(secs[hook_i], 1) if hook_i is not None else None,
        "ctaSec": round(secs[cta_i], 1) if cta_i is not None else None,
        "longestBlock": {"block": longest, "sec": round(secs[longest], 1)} if longest is not None else None,
        "secondsBeforePayoff": round(starts[payoff_index], 1) if payoff_index is not None else None,
        "payoffPositionRatio": round(starts[payoff_index] / t, 2) if payoff_index is not None and t else None,
        "secondsBeforeFirstConcreteExample": round(starts[first_example], 1) if first_example is not None else None,
        "targetDurationSec": (_strategy_target(script)),
        "deltaFromTargetSec": None,
        "blockSeconds": [round(s, 1) for s in secs],
        "issues": [],
    }
    if pacing["targetDurationSec"] is not None:
        pacing["deltaFromTargetSec"] = round(t - pacing["targetDurationSec"], 1)  # descriptif, jamais signalé
    issues = pacing["issues"]
    if hook_i is not None and secs[hook_i] > config.hook_max_sec:
        issues.append(_issue(
            "hook_slow",
            f"Le hook dure {secs[hook_i]:.1f} s ({'mesuré' if source == 'measured' else 'estimé'}) "
            f"avant d'atteindre la suite (configuré : {config.hook_max_sec:g} s).",
            [hook_i],
        ))
    if config.max_block_sec is not None and longest is not None and secs[longest] > config.max_block_sec:
        issues.append(_issue("block_too_long", f"Bloc {longest + 1} : {secs[longest]:.1f} s.", [longest]))
    if (
        config.max_seconds_before_payoff is not None and payoff_index is not None
        and starts[payoff_index] > config.max_seconds_before_payoff
    ):
        issues.append(_issue(
            "payoff_late", f"Le payoff n'arrive qu'à {starts[payoff_index]:.1f} s.", [payoff_index],
        ))
    if (
        config.max_seconds_before_first_example is not None and first_example is not None
        and starts[first_example] > config.max_seconds_before_first_example
    ):
        issues.append(_issue(
            "example_late", f"Premier exemple concret à {starts[first_example]:.1f} s.", [first_example],
        ))
    return pacing


# --------------------------------------------------------------------------
# 5. Boucles ouvertes + promesses
# --------------------------------------------------------------------------

def analyze_open_loops(script, blocks, roles, payoff_index, payoff_source, starts, config) -> dict:
    cs = _strategy(script)
    declared = normalize_open_loops(script)
    loops: list[dict] = []
    cta_i = _cta_index(blocks)
    issues: list[dict] = []
    n = len(blocks)

    for k, raw in enumerate(declared):
        opened, resolved = raw.get("openedAtBlock"), raw.get("resolvedAtBlock")
        question = str(raw.get("question") or "")
        entry = {"question": question, "openedAtBlock": opened, "resolvedAtBlock": resolved, "declared": True}
        valid_open = isinstance(opened, int) and 0 <= opened < n
        valid_res = isinstance(resolved, int) and 0 <= resolved < n
        if resolved is None or not valid_res:
            entry["status"] = "unresolved"
            issues.append(_issue(
                "unresolved_loop", f"La question « {question} » n'est jamais résolue.", severity="high",
            ))
        elif valid_open and resolved < opened:
            entry["status"] = "invalid"
            issues.append(_issue(
                "loop_resolved_before_opened", f"La boucle « {question} » est résolue avant d'être ouverte.",
                [resolved, opened], severity="high",
            ))
        else:
            entry["status"] = "resolved"
            terms = set(_content_tokens(question))
            window = " ".join(blocks[j].get("text", "") for j in {resolved, payoff_index} if j is not None)
            overlap = len(terms & set(_content_tokens(window)))
            entry["lexicalOverlap"] = overlap
            entry["delayBlocks"] = (resolved - opened) if valid_open else None
            entry["delaySec"] = round(starts[resolved] - starts[opened], 1) if valid_open else None
            if cta_i is not None and resolved >= cta_i:
                issues.append(_issue(
                    "resolved_by_cta", f"La question « {question} » n'est résolue que par le CTA.", [resolved],
                    severity="high",
                ))
            elif terms and overlap == 0:
                issues.append(_issue(
                    "resolution_not_matching",
                    f"Le bloc {resolved + 1} censé résoudre « {question} » n'en reprend aucun terme.", [resolved],
                ))
        loops.append(entry)

    # Boucle implicite : la question centrale du contentStrategy, ouverte au hook.
    if not declared and cs.get("coreQuestion"):
        loops.append({
            "question": cs["coreQuestion"], "openedAtBlock": _hook_index(blocks),
            "resolvedAtBlock": payoff_index, "declared": False,
            "status": "resolved" if payoff_index is not None else "unresolved",
        })
        if payoff_index is None:
            issues.append(_issue(
                "unresolved_loop", "La question centrale du hook n'a aucun bloc de payoff.", severity="high",
            ))

    # Promesses du type « à la fin », « voici pourquoi » sans résolution.
    promises = []
    cta_limit = cta_i if cta_i is not None else n
    for i, b in enumerate(blocks[:cta_limit]):
        cue = _contains_any(b.get("text", ""), _PROMISE_CUES)
        if cue:
            promises.append({"block": i, "cue": cue.strip()})
    resolved_any = any(l["status"] == "resolved" for l in loops)
    if promises and not resolved_any and payoff_source in ("none", "last_body_block", "cta_only"):
        issues.append(_issue(
            "promise_without_resolution",
            f"Bloc {promises[0]['block'] + 1} : promesse (« {promises[0]['cue']} ») sans réponse identifiable.",
            [promises[0]["block"]], severity="high",
        ))

    # Les boucles ouvertes sont facultatives : l'absence de boucle n'est jamais un défaut.
    return {"loops": loops, "promises": promises, "issues": issues}


# --------------------------------------------------------------------------
# 6. Payoff
# --------------------------------------------------------------------------

def analyze_payoff(script, blocks, roles, payoff_index, payoff_source, hook_diag) -> dict:
    cs = _strategy(script)
    hook_i = _hook_index(blocks)
    cta_i = _cta_index(blocks)
    issues: list[dict] = []
    out = {
        "blockIndex": payoff_index, "source": payoff_source,
        "resolvesHook": None, "concreteValue": None, "genericAdvice": None, "issues": issues,
    }
    if payoff_index is None:
        issues.append(_issue("payoff_missing", "Aucun bloc de payoff identifiable.", severity="high"))
        return out

    text = blocks[payoff_index].get("text", "")
    out["text"] = text
    out["concreteValue"] = _has_number(text)
    generic = _contains_any(text, _GENERIC_ADVICE)
    out["genericAdvice"] = generic is not None
    if generic and not out["concreteValue"]:
        # « high » seulement quand le payoff TIENT dans une formule creuse (court) ; un payoff long qui
        # contient une formule creuse parmi d'autres éléments reste un simple signalement.
        short = len(_words(text)) <= 14
        issues.append(_issue(
            "generic_payoff", "Le payoff est un conseil générique sans valeur concrète.", [payoff_index],
            severity="high" if short else "info",
        ))

    # Le hook est-il résolu ? Chevauchement lexical entre la question (ou le
    # hook) et le payoff / la révélation — indicatif, pas une preuve.
    question = cs.get("coreQuestion") or (blocks[hook_i].get("text", "") if hook_i is not None else "")
    reward_text = " ".join(
        blocks[i].get("text", "") for i, r in enumerate(roles)
        if r["role"] in ("reveal", "payoff") and blocks[i].get("role") != "cta"
    ) or text
    terms = set(_content_tokens(question))
    overlap = len(terms & set(_content_tokens(reward_text)))
    out["lexicalOverlap"] = overlap
    out["resolvesHook"] = overlap > 0 or bool(hook_diag.get("containsSpecificNumber") and out["concreteValue"])
    if terms and not out["resolvesHook"]:
        # Recouvrement lexical = indice faible (paraphrase, synonymes) : jamais « high ».
        issues.append(_issue(
            "payoff_not_resolving_hook",
            "Le payoff ne reprend aucun terme du hook : la promesse n'est pas explicitement résolue.",
            [payoff_index], severity="info",
        ))
    if hook_diag.get("containsSpecificNumber") and not out["concreteValue"] and out["resolvesHook"] is not True:
        issues.append(_issue(
            "payoff_without_number", "Le hook s'appuie sur un chiffre mais le payoff n'en donne aucun.", [payoff_index],
        ))

    # Ce que le plan annonce (contentStrategy.payoff) apparaît-il vraiment ?
    promised = cs.get("payoff")
    if isinstance(promised, str) and promised.strip():
        body_text = " ".join(b.get("text", "") for i, b in enumerate(blocks) if i != hook_i)
        body_numbers = _numbers(body_text)
        missing_numbers = sorted(n for n in _numbers(promised) if not _number_present(n, body_numbers))
        out["promisedNumbersMissing"] = missing_numbers
        if missing_numbers:
            # Écart ENTRE le plan (métadonnée du modèle) et le script, pas un défaut vu par le spectateur :
            # jamais « high ». Tolérant à l'arrondi (364 307 annoncé, « 364 000 » dit).
            issues.append(_issue(
                "promised_number_missing",
                f"Le plan annonce {', '.join(missing_numbers)} mais le script ne le dit pas.",
                severity="info",
            ))
        p_terms = set(_content_tokens(promised))
        if p_terms:
            ratio = len(p_terms & set(_content_tokens(text))) / len(p_terms)
            out["plannedPayoffOverlap"] = round(ratio, 2)

    # Le CTA ne doit pas remplacer le payoff.
    if cta_i is not None:
        cta_text = blocks[cta_i].get("text", "")
        if payoff_index == cta_i:
            issues.append(_issue("cta_replaces_payoff", "Le CTA tient lieu de payoff.", [cta_i], severity="high"))
    return out


# --------------------------------------------------------------------------
# 7. Progression visuelle + pattern interrupts
# --------------------------------------------------------------------------

def _scene_type(block: dict) -> str | None:
    mg = block.get("motion_graphic")
    if isinstance(mg, dict):
        value = mg.get("sceneType") or mg.get("type")
        return str(value) if value else None
    return None


def plan_visual_progression(blocks: list[dict], roles: list[dict]) -> list[dict]:
    """Recommandation par bloc : ce que le visuel doit FAIRE pour son rôle
    (progresser, pas illustrer). Déterministe ; n'applique rien."""
    plan = []
    for i, (b, r) in enumerate(zip(blocks, roles)):
        role = r["role"]
        plan.append({
            "block": i, "role": role,
            "intent": ROLE_VISUAL_INTENT.get(role or "", "illustrer le propos"),
            "preferredScenes": list(ROLE_SCENE_FIT.get(role or "", ())),
            "currentScene": _scene_type(b), "currentShot": b.get("shotType"),
        })
    return plan


def plan_pattern_interrupts(blocks: list[dict], roles: list[dict]) -> list[dict]:
    """Rupture de rythme visuelle de chaque bloc par rapport au précédent, à
    partir de `sceneType` / `shotType` existants (jamais d'effet gratuit)."""
    out = []
    prev_scene = prev_shot = None
    run = 0
    for i, b in enumerate(blocks):
        scene, shot = _scene_type(b), b.get("shotType")
        kind = None
        if i > 0:
            if scene and prev_scene and scene != prev_scene:
                kind = {"big_number": "number_reveal", "comparison": "comparison_state",
                        "before_after": "comparison_state", "warning": "typography_emphasis"}.get(
                    scene, "chart_appearance" if scene in _HEAVY_SCENES + ("progress_bar",) else "composition_change")
            elif shot and prev_shot and shot != prev_shot:
                kind = "framing_change"
        run = 0 if kind or i == 0 else run + 1
        suggestion = None
        if i > 0 and kind is None and run >= 2:
            role = roles[i]["role"] or ""
            options = [s for s in ROLE_SCENE_FIT.get(role, ()) if s != scene] if scene else []
            suggestion = options[0] if options else next((s for s in _ALTERNATIVE_SHOTS if s != shot), None)
        out.append({"block": i, "interrupt": kind, "stagnantRun": run, "suggestion": suggestion})
        prev_scene, prev_shot = scene or prev_scene, shot or prev_shot
    return out


def analyze_visual_progression(blocks, roles, config) -> dict:
    scenes = [_scene_type(b) for b in blocks]
    shots = [b.get("shotType") for b in blocks]
    signature = [s or sh for s, sh in zip(scenes, shots)]
    issues: list[dict] = []
    available = any(signature)
    result = {
        "available": available, "sceneTypes": scenes, "shotTypes": shots,
        "plan": plan_visual_progression(blocks, roles),
        "patternInterrupts": plan_pattern_interrupts(blocks, roles),
        "issues": issues,
    }
    if not available:
        return result

    # Même structure visuelle sur N plans consécutifs.
    start = 0
    for i in range(1, len(signature) + 1):
        if i == len(signature) or signature[i] != signature[start] or not signature[start]:
            length = i - start
            if signature[start] and length >= config.same_structure_run:
                idx = list(range(start, i))
                issues.append(_issue(
                    "same_visual_structure",
                    f"Blocs {_pretty(idx)} : {length} plans consécutifs avec la même structure visuelle (« {signature[start]} »).",
                    idx,
                ))
            start = i

    # Diapositives de chiffres indépendantes au lieu d'un état qui évolue.
    run: list[int] = []
    for i, s in enumerate(scenes + [None]):
        if s in _NUMERIC_SCENES:
            run.append(i)
            continue
        if len(run) >= config.number_slide_run:
            issues.append(_issue(
                "independent_number_slides",
                f"Blocs {_pretty(run)} : {len(run)} chiffres sur des scènes indépendantes ; préférer UNE scène dont "
                "l'état change (compteur, barre de progression, graphique).",
                run,
            ))
        run = []

    for i, (s, r) in enumerate(zip(scenes, roles)):
        if r["role"] == "cta" and s in _HEAVY_SCENES:
            issues.append(_issue(
                "heavy_cta_visual", f"CTA sur une scène « {s} » : garder un visuel minimal et non distrayant.", [i],
            ))
    result["roleFitMismatches"] = [
        {"block": i, "role": r["role"], "scene": s}
        for i, (s, r) in enumerate(zip(scenes, roles))
        if s and r["role"] and s not in ROLE_SCENE_FIT.get(r["role"], (s,))
    ]
    return result


# --------------------------------------------------------------------------
# 8. CTA + série
# --------------------------------------------------------------------------

def detect_cta_intent(text: str, series: dict | None = None) -> str | None:
    text = str(text or "")
    if not text.strip():
        return "none"
    for intent in ("next_episode", "subscribe", "save", "share"):
        if _contains_any(text, _CTA_PATTERNS[intent]):
            return intent
    if _contains_any(text, _CTA_PATTERNS["follow_for_series"]):
        return "follow_for_series"
    if "?" in text:
        return "question"
    return None


def analyze_cta(script, blocks, config) -> dict:
    cs = _strategy(script)
    series = script.get("series") if isinstance(script.get("series"), dict) else None
    cta_i = _cta_index(blocks)
    text = str(script.get("cta") or (blocks[cta_i].get("text") if cta_i is not None else "") or "")
    declared = cs.get("ctaIntent")
    detected = detect_cta_intent(text, series)
    words = len(_words(text))
    issues: list[dict] = []
    if _contains_any(text, _CTA_BOILERPLATE) and declared != "subscribe":
        issues.append(_issue(
            "boilerplate_cta", "CTA générique « like / abonne-toi » plaqué sans intention déclarée.",
            [cta_i] if cta_i is not None else None,
        ))
    if words > config.cta_max_words:
        issues.append(_issue("cta_too_long", f"CTA de {words} mots (configuré : {config.cta_max_words} maximum).",
                             [cta_i] if cta_i is not None else None))
    # Intention déclarée vs CTA présent : écart de MÉTADONNÉES (le modèle déclare « save » puis n'écrit aucun CTA),
    # invisible pour le spectateur : rapporté dans `declaredIntent`/`detectedIntent`, jamais un défaut.
    # Intention déclarée vs intention détectée : métadonnées seulement (voir plus haut), jamais un défaut.
    if declared == "next_episode" and not series:
        issues.append(_issue("next_episode_without_series", "CTA « next_episode » sans métadonnées de série."))
    if series and series.get("continuityCTA") and len(_words(series["continuityCTA"])) > config.cta_max_words:
        issues.append(_issue("continuity_cta_too_long", "Le CTA de continuité de la série est trop long."))
    return {
        "text": text, "wordCount": words, "declaredIntent": declared, "detectedIntent": detected,
        "series": ({"name": series.get("name"), "episode": series.get("episode"),
                    "continuityCTA": series.get("continuityCTA")} if series else None),
        "issues": issues,
    }


# --------------------------------------------------------------------------
# Rapport complet
# --------------------------------------------------------------------------

def analyze_integrity(script: dict, blocks: list[dict]) -> list[dict]:
    """Contrôles d'intégrité du contenu (engine/integrity.py) : étroits, déterministes, sévérité « high »
    seulement pour une forme reconnue sans ambiguïté."""
    issues: list[dict] = []
    for item in integrity.find_arithmetic_inconsistencies(blocks):
        issues.append(_issue(
            "arithmetic_inconsistency",
            f"Bloc {item['block'] + 1} : calcul incohérent ({item['claim']}), attendu environ {item['expected']:g}.",
            [item["block"]], severity="high",
        ))
    for item in integrity.find_projection_issues(blocks):
        if item["kind"] == "guaranteed":
            issues.append(_issue("guaranteed_language", f"Bloc {item['block'] + 1} : résultat présenté comme garanti.",
                                 [item["block"]], severity="high"))
        else:
            what = "aucun rendement annoncé" if item["kind"] == "rate_unstated" else "projection non présentée comme hypothétique"
            issues.append(_issue("projection_assumption_missing", f"Bloc {item['block'] + 1} : projection chiffrée sans hypothèse explicite ({what}).",
                                 [item["block"]], severity="high"))
    for item in integrity.find_unsupported_empirical_claims(script):
        issues.append(_issue("unsupported_empirical_claim",
                             f"Bloc {item['block'] + 1} : affirmation empirique sans source (« {item['phrase']} »).",
                             [item["block"]], severity="high"))
    promises = integrity.find_cta_promises(blocks)
    if promises:
        issues.append(_issue("unsupported_cta_promise",
                             f"Bloc(s) {_pretty(promises)} : le CTA promet une ressource, une réponse ou un message que le produit ne fournit pas.",
                             promises, severity="high"))
    placeholders = integrity.find_placeholders([_viewer_strings(b) for b in blocks])
    if placeholders:
        issues.append(_issue("viewer_placeholder", f"Bloc(s) {_pretty(placeholders)} : texte de remplissage visible ($X, [valeur], example…).",
                             placeholders, severity="high"))
    return issues


def analyze(
    script: dict,
    durations: list[float] | None = None,
    config: RetentionConfig = DEFAULT_CONFIG,
    scene_reports: list[dict] | None = None,
) -> dict:
    """Rapport `retentionDiagnostics` : descriptif, factuel, SANS score ni
    probabilité de viralité. `durations` : durées voix off mesurées par bloc
    (sinon estimées depuis le nombre de mots)."""
    blocks = _body_blocks(script)
    language = script.get("language") or "fr"
    roles = assign_retention_roles(blocks)
    hook_i = _hook_index(blocks)
    cs = _strategy(script)
    hook_text = blocks[hook_i].get("text", "") if hook_i is not None else ""

    hook = diagnose_hook(hook_text, cs.get("hookType"), script.get("title"), config)
    if cs.get("hookText") and hook_text:
        a, b = set(_content_tokens(cs["hookText"])), set(_content_tokens(hook_text))
        if a and b and len(a & b) / len(a | b) < 0.5:
            hook["issues"].append(_issue(
                "hook_text_mismatch", "contentStrategy.hookText diffère du texte du bloc hook.",
            ))

    structure = analyze_structure(blocks, roles, config)
    payoff_index, payoff_source = find_payoff_index(blocks, roles)
    pacing = analyze_pacing(blocks, roles, durations, language, config, payoff_index, script)
    starts = []
    t = 0.0
    for s in pacing["blockSeconds"]:
        starts.append(t)
        t += s
    loops = analyze_open_loops(script, blocks, roles, payoff_index, payoff_source, starts, config)
    payoff = analyze_payoff(script, blocks, roles, payoff_index, payoff_source, hook)
    repetition = analyze_repetition(blocks, config)
    visual = analyze_visual_progression(blocks, roles, config)
    cta = analyze_cta(script, blocks, config)

    leaks = find_role_label_leaks(blocks)
    if leaks:
        structure["issues"].append(_issue(
            "role_label_leak",
            f"Bloc(s) {_pretty(leaks)} : une étiquette interne (pattern interrupt, reveal, resolution…) apparaît dans un texte lu ou affiché.",
            leaks, severity="high",
        ))
    personal = [] if script.get("source_type") == "pasted_text" else find_first_person_anecdotes(blocks)
    if personal:
        structure["issues"].append(_issue(
            "unsupported_first_person",
            f"Bloc(s) {_pretty(personal)} : expérience à la première personne présentée comme vécue, sans histoire fournie.",
            personal, severity="high" if len(personal) >= 2 else "info",
        ))
    structure["roleLabelLeaks"] = leaks
    structure["firstPersonBlocks"] = personal
    integrity_issues = analyze_integrity(script, blocks)
    # Repli de scène Motion Graphics (engine/motion_graphics/semantic.py) : le défaut a été CORRIGÉ avant le rendu,
    # donc simple information (jamais « high ») — mais RECORDÉ.
    fallbacks = [e for e in (scene_reports or []) if str(e.get("action", "")).startswith("fallback_")]
    if fallbacks:
        integrity_issues.append(_issue(
            "scene_data_fallback",
            f"Bloc(s) {_pretty([int(e['blockIndex']) for e in fallbacks])} : données de scène inutilisables, repli typographique "
            "(aucune valeur inventée).", [int(e["blockIndex"]) for e in fallbacks],
        ))

    sections = {
        "hook": hook["issues"], "structure": structure["issues"], "pacing": pacing["issues"],
        "openLoops": loops["issues"], "payoff": payoff["issues"], "repetition": repetition["issues"],
        "visualProgression": visual["issues"], "cta": cta["issues"], "integrity": integrity_issues,
    }
    issues = [{"section": name, **issue} for name, items in sections.items() for issue in items]
    report = {
        "version": VERSION,
        "hasContentStrategy": bool(cs),
        "hook": hook,
        "structure": structure,
        "pacing": pacing,
        "openLoops": loops["loops"],
        "promises": loops["promises"],
        "payoff": payoff,
        "repetition": repetition,
        "visualProgression": visual,
        "cta": cta,
        "issues": issues,
        "summary": [i["message"] for i in issues],
    }
    return report


def build_generation_metadata(script: dict, report: dict | None = None) -> dict:
    """Métadonnées de génération pour une future boucle d'analytique :

        vidéo (content_item_id) -> contentStrategy -> hookType -> structure
        narrative -> types de scène -> durée -> métriques observées

    Aucune métrique observée n'est collectée ici (pas d'API YouTube, pas de
    ML). `content_item_id` + l'identifiant de publication de la plateforme
    servent de clé de jointure côté base ; ce dictionnaire n'est que la face
    « génération » de la jointure."""
    report = report if report is not None else analyze(script)
    cs = _strategy(script)
    blocks = _body_blocks(script)
    series = script.get("series") if isinstance(script.get("series"), dict) else None
    return {
        "retentionEngineVersion": VERSION,
        "hookType": cs.get("hookType"),
        "ctaIntent": cs.get("ctaIntent") or report["cta"]["detectedIntent"],
        "narrativeStructure": report["structure"]["sequence"],
        "sceneTypes": [_scene_type(b) for b in blocks],
        "shotTypes": [b.get("shotType") for b in blocks],
        "nBlocks": len(blocks),
        "durationSec": report["pacing"]["totalSec"],
        "durationSource": report["pacing"]["durationSource"],
        "targetDurationSec": cs.get("targetDurationSec"),
        "language": script.get("language"),
        "visualStyle": script.get("visual_style"),
        "contentGoal": script.get("content_goal"),
        "series": {"name": series.get("name"), "episode": series.get("episode")} if series else None,
        "issueCodes": sorted({i["code"] for i in report["issues"]}),
    }


def empty_observed_metrics() -> dict:
    """Gabarit des métriques observées FUTURES (toutes à `None`). `views` et
    `engagedViews` sont deux champs distincts."""
    return {name: None for name in OBSERVED_METRIC_FIELDS}


def join_observation(metadata: dict, observed: dict) -> dict:
    """Associe métadonnées de génération et métriques observées. Rejette un
    champ inconnu au lieu de le laisser se glisser silencieusement."""
    unknown = sorted(set(observed) - set(OBSERVED_METRIC_FIELDS))
    if unknown:
        raise ValueError(f"métrique(s) observée(s) inconnue(s) : {unknown}")
    return {"generation": metadata, "observed": {**empty_observed_metrics(), **observed}}
