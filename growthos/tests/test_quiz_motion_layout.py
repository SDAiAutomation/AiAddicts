"""Contrôles de mise en page de la scène Motion : rien ne sort du cadre, le texte reste lisible.

La mise en page est calculée en fractions de la largeur et de la hauteur : ces tests analysent les événements ASS
produits (sans rendu vidéo) pour tous les formats pris en charge. Ils auraient détecté le texte à 56 % de sa taille
en 16:9 (growthos PR #26)."""
import json
import re
import unittest
from pathlib import Path

from engine.captions import _quiz_events
from engine.quiz import compile_quiz

RESOLUTIONS = ((720, 1280), (1080, 1920), (1080, 1080), (1920, 1080))
_POS = re.compile(r"\\(?:pos\((-?\d+),(-?\d+)\)|move\((-?\d+),(-?\d+),(-?\d+),(-?\d+))")
_FONT = re.compile(r"\\fs(\d+)")
_PATH = re.compile(r"m 0 0 l (\d+) 0 \d+ (\d+) 0 \d+")
# Décor qui partage le style de la question : lettres A-D, coche, numéros et « / 03 ».
_DECOR = re.compile(r"^(?:[A-D]|✓|\d{1,2}|/ \d{1,2})$")
# Les textes que le spectateur doit lire (le reste : lettres A-D, compteurs, décor).
_READABLE_STYLES = (",QuizQuestion,", ",QuizChoice,", ",QuizCorrect,")


def _parse(event: str) -> dict:
    pos = _POS.search(event)
    end = None
    if pos:
        end = (int(pos.group(5)), int(pos.group(6))) if pos.group(5) else (int(pos.group(1)), int(pos.group(2)))
    path = _PATH.search(event)
    font = _FONT.search(event)
    return {"end": end, "size": (int(path.group(1)), int(path.group(2))) if path else None,
            "font": int(font.group(1)) if font else None,
            "readable": any(s in event for s in _READABLE_STYLES) and not _DECOR.match(event.rsplit("}", 1)[-1].strip()),
            "an7": "\\an7" in event}


class QuizMotionLayoutTests(unittest.TestCase):
    def setUp(self):
        self.script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
        self.script["quiz"]["presentation"] = "motion"

    def _blocks(self, choices: int, long_answers: bool = False) -> list[dict]:
        question = self.script["quiz"]["questions"][0]
        names = ["Vénus", "Mercure", "Mars", "La Terre"][:choices]
        if long_answers:
            names = [f"Une réponse assez longue pour la rangée numéro {i + 1}" for i in range(choices)]
        question["choices"] = names
        question["correct_choice"] = 1
        blocks = compile_quiz(self.script)["blocks"]
        for block in blocks:
            block["quiz_visual_available"] = False
        return blocks

    def _all_scenes(self):
        for choices in (2, 3, 4):
            for long_answers in (False, True):
                blocks = self._blocks(choices, long_answers)
                for block in blocks:
                    if block.get("quiz_phase") in {"intro", "question", "reveal", "outro"}:
                        yield choices, long_answers, block

    def test_every_element_stays_inside_the_frame(self):
        for width, height in RESOLUTIONS:
            for choices, long_answers, block in self._all_scenes():
                for event in _quiz_events([block], [7], width, height):
                    parsed = _parse(event)
                    if parsed["end"] is None:
                        continue
                    x, y = parsed["end"]
                    label = (width, height, block["quiz_phase"], choices, long_answers)
                    self.assertTrue(-2 <= x <= width + 2 and -2 <= y <= height + 2, (label, event[:120]))
                    if parsed["size"] and parsed["an7"]:
                        self.assertLessEqual(x + parsed["size"][0], width + 2, (label, "dépasse à droite"))
                        self.assertLessEqual(y + parsed["size"][1], height + 2, (label, "dépasse en bas"))

    def test_questions_and_answers_stay_readable_at_every_format(self):
        for width, height in RESOLUTIONS:
            minimum = 0.0185 * height
            for choices, long_answers, block in self._all_scenes():
                for event in _quiz_events([block], [7], width, height):
                    parsed = _parse(event)
                    # Pendant la révélation, la bonne réponse est affichée en grand ; la clé des réponses
                    # (rangées compactes) est un rappel secondaire, volontairement plus petit.
                    in_key = block["quiz_phase"] == "reveal" and (",QuizChoice," in event or ",QuizCorrect," in event)
                    if parsed["readable"] and parsed["font"] is not None and not in_key:
                        self.assertGreaterEqual(
                            parsed["font"], minimum,
                            (width, height, block["quiz_phase"], choices, long_answers, parsed["font"]))

    def test_landscape_text_is_not_smaller_than_portrait_text_relative_to_the_screen(self):
        question = self._blocks(4)[1]
        def biggest(width, height):
            return max(_parse(e)["font"] or 0 for e in _quiz_events([question], [7], width, height) if _parse(e)["readable"])
        # Le texte le plus grand en 16:9 est au moins aussi grand, en proportion de la hauteur d'écran, que le texte vertical.
        self.assertGreaterEqual(biggest(1920, 1080) / 1080, 0.9 * biggest(1080, 1920) / 1920)


if __name__ == "__main__":
    unittest.main()
