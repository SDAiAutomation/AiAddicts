"""French spoken form of simple algebra, leaving the displayed equation intact."""

import re


def for_voice(text: str) -> str:
    """Spell the variable x and common equation operators for French TTS."""
    text = re.sub(
        r"(?i)(?<![a-z])x(?![a-z])",
        lambda match: (" " if match.start() and text[match.start() - 1].isdigit() else "") + "iks",
        text,
    )
    text = re.sub(r"\s*([+=])\s*", lambda m: " plus " if m[1] == "+" else " égale ", text)
    return re.sub(r"\s+", " ", text).strip()
