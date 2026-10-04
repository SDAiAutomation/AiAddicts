"""Contrôles éditoriaux simples orientés rétention short-form."""
import re
import unicodedata


# Lexiques par langue (fr, en, es, de, it, pt : les langues de la génération).
# Entrées comparées SANS accents ni casse. Un mot seul = mot entier exact ; un
# mot terminé par « * » = début de mot (erreur* couvre erreur, erreurs) ; une
# entrée avec espace = expression. Le détecteur reste une heuristique de mots-clés :
# il signale un doute, il ne juge pas la qualité.
_LEXICONS: dict[str, dict[str, tuple[str, ...]]] = {
    "fr": {
        "generic": ("voici", "tu veux", "vous voulez", "dans cette video", "aujourd'hui",
                    "saviez-vous", "le savais-tu", "bonjour"),
        "curiosity": ("erreur*", "jamais", "pourquoi", "secret*", "personne", "sans", "avant",
                      "sauf", "mais", "pourtant", "evit*", "arret*", "contraire", "verite",
                      "mensonge*", "faux", "piege*", "danger*", "interdit*", "cach*",
                      "vide", "videe", "videes", "vides", "perdu*", "perdre", "vole*", "ruine*", "detruit*", "pirate*", "arnaque*"),
        "numbers": ("deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
                    "douze", "vingt", "trente", "cent", "mille", "million*", "milliard*"),
        "claims": ("premier", "premiere", "dernier", "derniere", "seul", "seule", "unique", "record"),
    },
    "en": {
        "generic": ("here is", "here's", "here are", "in this video", "today", "did you know",
                    "do you want", "hello", "hi guys", "welcome"),
        "curiosity": ("mistake*", "never", "why", "secret*", "nobody", "no one", "without", "before",
                      "except", "but", "yet", "stop", "avoid*", "wrong", "truth", "lie", "lies",
                      "myth*", "hidden", "actually", "danger*", "warning", "banned", "forbidden",
                      "emptied", "drain*", "lost", "stole", "stolen", "ruined", "destroyed", "hacked", "scam*"),
        "numbers": ("two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                    "twelve", "twenty", "thirty", "hundred", "thousand", "million*", "billion*"),
        "claims": ("first", "last", "only", "oldest", "largest", "smallest", "fastest", "worst", "best"),
    },
    "es": {
        "generic": ("aqui tienes", "en este video", "hoy", "sabias que", "quieres", "hola", "bienvenido"),
        "curiosity": ("error*", "nunca", "jamas", "por que", "secreto*", "nadie", "sin", "antes",
                      "salvo", "pero", "sin embargo", "evita*", "contrario", "verdad", "mentira*",
                      "trampa*", "peligro*", "prohibido*", "oculto*",
                      "vacio", "vacia", "perdio", "perdi*", "robo", "robaron", "robado", "arruin*", "estaf*", "hackea*"),
        "numbers": ("dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
                    "veinte", "treinta", "cien", "mil", "millon*", "millones"),
        "claims": ("primer", "primera", "primero", "ultimo", "ultima", "unico", "unica", "record"),
    },
    "de": {
        "generic": ("hier ist", "in diesem video", "heute", "wusstest du", "willst du", "hallo", "willkommen"),
        "curiosity": ("fehler*", "nie", "niemals", "warum", "geheim*", "niemand", "ohne", "bevor",
                      "ausser", "aber", "doch", "trotzdem", "stopp", "vermeide*", "wahrheit", "luge*",
                      "mythos", "versteckt*", "verboten*", "gefahr*",
                      "geleert", "verlor*", "gestohlen", "ruinier*", "betrug", "gehackt"),
        "numbers": ("zwei", "drei", "vier", "funf", "sechs", "sieben", "acht", "neun", "zehn",
                    "zwanzig", "hundert", "tausend", "million*"),
        "claims": ("erste*", "letzte*", "einzige*", "rekord"),
    },
    "it": {
        "generic": ("ecco", "in questo video", "oggi", "sapevi che", "vuoi", "ciao", "benvenuto"),
        "curiosity": ("error*", "mai", "perche", "segret*", "nessuno", "senza", "prima", "tranne",
                      "ma", "eppure", "evita*", "smetti", "contrario", "verita", "bugia*", "trappola*",
                      "pericol*", "vietat*", "nascost*",
                      "svuot*", "perso", "persa", "rubat*", "rovinat*", "truffa*", "hackerat*"),
        "numbers": ("due", "tre", "quattro", "cinque", "sette", "otto", "nove", "dieci", "venti",
                    "trenta", "cento", "mille", "milion*"),
        "claims": ("primo", "ultimo", "unico", "record"),
    },
    "pt": {
        "generic": ("aqui esta", "neste video", "hoje", "voce sabia", "voce quer", "ola", "bem-vindo"),
        "curiosity": ("erro*", "nunca", "jamais", "por que", "segredo*", "ninguem", "sem", "antes",
                      "exceto", "mas", "porem", "no entanto", "evite*", "pare", "contrario", "verdade",
                      "mentira*", "armadilha*", "perigo*", "proibid*", "escondid*",
                      "esvazi*", "perdeu", "perdi*", "roub*", "arruin*", "golpe*", "hackead*"),
        "numbers": ("dois", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
                    "vinte", "trinta", "cem", "mil", "milh*"),
        "claims": ("primeiro", "primeira", "ultimo", "ultima", "unico", "unica", "recorde"),
    },
}
_WORD_RE = re.compile(r"\b[\wÀ-ÿ'’-]+\b", re.UNICODE)
_LETTERS_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
# Les "visual" sont toujours en français (consigne au générateur d'images).
_WIDE_SHOT_PREFIXES = ("plan large", "plan d'ensemble", "vue d'ensemble", "vue large", "panoramique")
_MAX_TITLE_CHARS = 60  # le prompt demande 50 ; signalé au-delà, mais SANS retirer de points :
# le titre est la phrase d'idée saisie par l'utilisateur (benchmark 2026-10-04 : 5 vidéos sur 6),
# pas un défaut du script ; il passait quand même la vidéo en quality_check à lui seul avec le CTA.
_CTA_TARGET_WORDS = 12  # cible du prompt, signalée au-delà
_CTA_PENALTY_WORDS = 15  # pénalité seulement au-delà : le modèle écrit 13 mots quand on en demande 12
_NO_CAPITAL_NOUNS = {"de"}  # en allemand tous les noms prennent une majuscule : pas un indice


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.strip())


def _fold(text: str) -> str:
    """Minuscules, sans accents, apostrophes droites."""
    decomposed = unicodedata.normalize("NFD", text.replace("’", "'").lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _lexicon(language: str | None) -> dict[str, tuple[str, ...]]:
    """Lexique de la langue du script ; langue inconnue = union de toutes (indulgent)."""
    code = (language or "fr").strip().lower()[:2]
    if code in _LEXICONS:
        return _LEXICONS[code]
    merged: dict[str, tuple[str, ...]] = {}
    for lexicon in _LEXICONS.values():
        for key, entries in lexicon.items():
            merged[key] = merged.get(key, ()) + entries
    return merged


def _matches(entries: tuple[str, ...], folded_text: str, tokens: list[str]) -> bool:
    for entry in entries:
        if " " in entry:
            if re.search(rf"\b{re.escape(entry)}\b", folded_text):
                return True
        elif entry.endswith("*"):
            stem = entry[:-1]
            if any(token.startswith(stem) for token in tokens):
                return True
        elif entry in tokens:
            return True
    return False


def _has_proper_noun(hook: str) -> bool:
    """Un nom propre (Terre, NASA, Einstein) ailleurs qu'en début de phrase :
    l'accroche vise quelque chose de précis."""
    tokens = _LETTERS_RE.findall(hook)
    for token in tokens[1:]:
        if len(token) > 1 and token[0].isupper():
            return True
    return False


def analyze_script(script: dict) -> dict:
    """Retourne un score et des problèmes actionnables, sans appel externe."""
    blocks = script.get("blocks") or []
    hook = next((str(b.get("text") or "") for b in blocks if b.get("role") == "hook"), "")
    cta = str(script.get("cta") or next(
        (b.get("text") or "" for b in blocks if b.get("role") == "cta"), ""
    ))
    hook_words = _words(hook)
    cta_words = _words(cta)
    language = str(script.get("language") or "fr")
    issues: list[str] = []
    score = 100

    if not hook:
        score -= 60
        issues.append("Aucun hook explicite.")
    else:
        if len(hook_words) < 5:
            score -= 15
            issues.append("Hook trop court pour installer une promesse claire.")
        elif len(hook_words) > 18:
            score -= 20
            issues.append(f"Hook trop long ({len(hook_words)} mots, cible : 5–18).")

        lexicon = _lexicon(language)
        folded = _fold(hook).strip()
        tokens = _LETTERS_RE.findall(folded)
        generic_start = next((p for p in lexicon["generic"] if folded.startswith(p)), None)
        has_number = bool(re.search(r"\d", hook)) or _matches(lexicon["numbers"], folded, tokens)
        has_curiosity = _matches(lexicon["curiosity"], folded, tokens)
        has_claim = _matches(lexicon["claims"], folded, tokens)
        has_name = language.strip().lower()[:2] not in _NO_CAPITAL_NOUNS and _has_proper_noun(hook)
        has_question = "?" in hook or "¿" in hook
        if generic_start and not (has_number or has_curiosity):
            score -= 20
            issues.append(f"Ouverture générique (« {generic_start} ») sans tension ni curiosité.")
        if not (has_number or has_curiosity or has_claim or has_name or has_question):
            score -= 10
            issues.append("Hook sans élément concret, question ou contraste identifiable.")

    hook_block = next((b for b in blocks if b.get("role") == "hook"), None)
    hook_visual = str((hook_block or {}).get("visual") or "").strip().lower()
    if hook_visual.startswith(_WIDE_SHOT_PREFIXES):
        # Le titre promet un élément précis ; ouvrir sur un plan de situation
        # (rue, décor) fait décrocher avant que la promesse n'apparaisse.
        score -= 10
        issues.append("Hook filmé en plan large : ouvrir sur un gros plan de l'élément promis par le titre.")

    title = str(script.get("title") or "").strip()
    if len(title) > _MAX_TITLE_CHARS:
        issues.append(f"Titre de {len(title)} caractères (cible : {_MAX_TITLE_CHARS} maximum, lisible en entier sur mobile).")

    if len(cta_words) > _CTA_TARGET_WORDS:
        if len(cta_words) > _CTA_PENALTY_WORDS:
            score -= 15
        issues.append(f"CTA trop long ({len(cta_words)} mots, cible : {_CTA_TARGET_WORDS} maximum).")

    return {
        "score": max(score, 0),
        "issues": issues,
        "hookWords": len(hook_words),
        "ctaWords": len(cta_words),
    }
