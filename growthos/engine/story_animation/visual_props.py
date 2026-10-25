"""Objects the scene can draw next to the narration: a word in the dialogue brings the matching object on screen (pure, no IO).

The list is closed on purpose: every id has a drawing in godot/rig_v1/scene.gd. Words are matched whole, case- and accent-blind, in
French and English, so a story never needs a new field and the author's text stays the only source of truth."""
from __future__ import annotations

import re
import unicodedata

OBJECT_SECONDS = 2.6      # an object stays on screen about this long after the word, never past its line
# object id -> words or phrases that call it (accents are stripped before matching)
LEXICON = {
    "book": ["dictionnaire", "livre", "roman", "1984", "dictionary", "book", "novel"],
    "umbrella": ["parapluie", "umbrella"],
    "key": ["cle", "clef", "key"],
    "lines3": ["trois lignes", "three lines"],
    "stamp": ["comite", "tampon", "committee", "stamp"],
    "compass": ["points cardinaux", "boussole", "compass", "cardinal directions"],
    "coin": ["salaire", "prime", "salary", "bonus", "wage"],
}
OBJECT_IDS = tuple(LEXICON)
# concrete things a story often names that the scene cannot draw yet: reported by the coherence review, never drawn
UNDRAWABLE = ["enseigne", "lettre", "valise", "telephone", "voiture", "train", "bateau", "fenetre", "journal", "affiche", "chapeau haut",
              "sign", "letter", "suitcase", "phone", "car", "boat", "newspaper", "poster"]


def fold(text: str) -> str:
    """Lowercase without accents, same length class as the input for matching."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _pattern(words: list) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?![a-z0-9])")


_PATTERNS = {oid: _pattern(words) for oid, words in LEXICON.items()}
_UNDRAWABLE = _pattern(UNDRAWABLE)
_NEGATION = re.compile(r"(?:\bpas de |\bsans |\baucun |\bno |\bwithout |\bn.a pas d.un? )$")


def mentions(text: str) -> list:
    """[(object id, position as a fraction of the text)] in order of appearance, one entry per object."""
    folded = fold(text)
    if not folded:
        return []
    found = []
    for oid, pat in _PATTERNS.items():
        for m in pat.finditer(folded):
            if _NEGATION.search(folded[max(0, m.start() - 14):m.start()]):
                continue          # "pas de parapluie": the object is absent, so it is not shown
            found.append((oid, m.start() / len(folded)))
            break
    return sorted(found, key=lambda x: x[1])


def undrawable(text: str) -> list:
    return sorted({m.group(0) for m in _UNDRAWABLE.finditer(fold(text))})


def schedule(text: str, start: float, dur: float) -> list:
    """Objects for one spoken line starting at `start` for `dur` seconds: [{id, start, end}], each shown from the word to the line end
    (at most OBJECT_SECONDS), and cut short when the next object appears."""
    events = []
    for oid, frac in mentions(text):
        a = round(start + dur * frac, 3)
        events.append({"id": oid, "start": a, "end": round(min(a + OBJECT_SECONDS, start + dur + 0.4), 3)})
    for prev, nxt in zip(events, events[1:]):
        prev["end"] = round(min(prev["end"], nxt["start"]), 3)
    return [e for e in events if e["end"] - e["start"] >= 0.5]
