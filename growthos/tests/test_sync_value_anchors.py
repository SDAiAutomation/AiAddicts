"""D1 a D4 de l'audit voix / visuel : les valeurs affichees apparaissent quand la voix les dit.

Les mots et les scenes ci-dessous sont les blocs reels du benchmark (PocketLogic, explainer, finance FR)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.motion_graphics import sync
from engine.motion_graphics.scenes import RENDERERS
from engine.motion_graphics.theme import resolve_theme


def words(*pairs):
    return [{"text": text, "start": start, "end": start + 0.3} for text, start in pairs]


def seconds(scene, ws, duration):
    out = sync.attach_reveals(scene, ws, duration)
    return [round(r * duration, 2) for r in out["_reveals"]] if "_reveals" in out else None


class TestNumberHelpers(unittest.TestCase):
    def test_digit_keys_reduce_grouped_amounts(self):
        self.assertEqual(sync.digit_keys("+ $38,300 GROWTH"), ["38300"])
        self.assertEqual(sync.digit_keys("3 000 dollars"), ["3000"])
        self.assertEqual(sync.digit_keys("Year 5"), ["5"])
        self.assertEqual(sync.digit_keys("REVENU"), [])

    def test_number_index_concatenates_split_tokens(self):
        ws = words(("Si", 0), ("gagnes", 0.4), ("3", 0.61), ("000", 0.77), ("dollars", 0.95))
        self.assertEqual(sync.number_index(ws, "3000"), 2)
        self.assertIsNone(sync.number_index(ws, "300"))

    def test_item_numbers_use_values_not_labels(self):
        scene = {"sceneType": "compound_growth", "data": [{"label": "Year 5", "displayValue": "$10,500"},
                                                          {"label": "Year 10", "displayValue": "$25,200"}]}
        self.assertEqual(sync.item_numbers(scene), [["10500"], ["25200"]])


class TestValueFirstReveals(unittest.TestCase):
    def test_d2_a_misleading_label_match_is_overridden_by_the_spoken_value(self):
        # « Year 5 » correspondait a « yearly » (0,53 s) : $10,500 s'affichait 2,3 s avant d'etre dit.
        ws = words(("Invest", 0.0), ("it", 0.41), ("yearly", 0.53), ("at", 0.88), ("an", 1.02), ("assumed", 1.14),
                   ("7%", 1.53), ("return:", 2.01), ("about", 2.45), ("$10,500", 2.77), ("after", 4.19),
                   ("five", 4.46), ("years,", 4.7), ("$25,200", 5.05), ("after", 6.0), ("ten", 6.2), ("years.", 6.5))
        scene = {"sceneType": "compound_growth", "title": "Assumed 7% a year",
                 "data": [{"label": "Year 5", "displayValue": "$10,500"}, {"label": "Year 10", "displayValue": "$25,200"}]}
        first, second = seconds(scene, ws, 7.245)
        self.assertAlmostEqual(first, 2.77 - sync.LEAD_SECONDS, places=2)   # jamais avant la valeur dite
        self.assertGreater(second, first)

    def test_d3_a_row_is_shown_when_its_amount_is_said_not_when_its_label_is(self):
        # « left over » est dit a 2,9 s mais « $150 » a 0,58 s : la ligne apparaissait a 2,84 s.
        ws = words(("So", 0.0), ("only", 0.29), ("$150", 0.58), ("of", 1.57), ("your", 1.65), ("$1,000", 1.81),
                   ("raise", 2.52), ("is", 2.77), ("left", 2.9), ("over.", 3.13))
        scene = {"sceneType": "money_split", "title": "Where the raise went",
                 "data": [{"label": "Spent", "displayValue": "$850"}, {"label": "Left over", "displayValue": "$150"}]}
        reveals = seconds(scene, ws, 3.622)
        self.assertLessEqual(reveals[1], 0.58)
        self.assertGreaterEqual(reveals[1], 0.0)

    def test_d3_a_grouped_amount_in_a_formula_term_is_found(self):
        ws = words(("Time", 0.0), ("did", 0.3), ("about", 0.5), ("$38,300", 0.69), ("of", 1.4), ("the", 1.5), ("work", 1.6),
                   ("over", 2.0), ("those", 2.3), ("20", 2.88), ("years,", 3.1), ("not", 3.5), ("you.", 3.82))
        scene = {"sceneType": "formula", "terms": ["$36,500 YOU", "+ $38,300 GROWTH", "= $74,800"]}
        reveals = seconds(scene, ws, 4.319)
        self.assertIsNotNone(reveals)
        self.assertLessEqual(reveals[1], 0.69)   # la ligne « $38,300 » suit la voix (elle arrivait a 1,8 s)

    def test_d4_value_never_appears_before_it_is_said(self):
        ws = words(("A", 0.0), ("pricier", 0.2), ("apartment", 0.56), ("adds", 0.9), ("$400.", 1.2),
                   ("A", 1.7), ("car", 2.0), ("payment", 2.35), ("adds", 2.7), ("$300.", 3.11))
        scene = {"sceneType": "bar_chart", "data": [{"label": "Apartment", "displayValue": "$400"},
                                                    {"label": "Car payment", "displayValue": "$300"}]}
        first, second = seconds(scene, ws, 4.0)
        self.assertAlmostEqual(first, 1.2 - sync.LEAD_SECONDS, places=2)
        self.assertAlmostEqual(second, 3.11 - sync.LEAD_SECONDS, places=2)

    def test_label_only_scenes_are_unchanged(self):
        # formule FR du benchmark : aucune valeur, les libelles pilotent comme avant.
        ws = words(("La", 0.0), ("regle", 0.21), ("est", 0.5), ("simple", 0.7), ("revenu", 1.1), ("moins", 1.4),
                   ("epargne", 1.76), ("egale", 2.2), ("budget", 2.6), ("de", 3.0), ("depense.", 3.2))
        scene = {"sceneType": "formula", "title": "La regle", "terms": ["REVENU", "- EPARGNE", "= BUDGET"]}
        reveals = seconds(scene, ws, 3.715)
        self.assertEqual(reveals, [0.98, 1.64, 2.48])

    def test_no_words_falls_back_to_the_even_stagger(self):
        scene = {"sceneType": "bar_chart", "data": [{"label": "A", "displayValue": "$1"}, {"label": "B", "displayValue": "$2"}]}
        self.assertIs(sync.attach_reveals(scene, [], 3.0), scene)
        self.assertIsNone(sync.compute_reveals(scene, [], 3.0))

    def test_a_value_is_matched_only_once_and_in_order(self):
        ws = words(("Save", 2.45), ("half", 2.75), ("the", 2.95), ("raise", 3.08), ("before", 3.3), ("lands:", 3.7), ("$500.", 4.12))
        scene = {"sceneType": "formula", "terms": ["$1,000 RAISE", "- $500 SAVED FIRST", "= $500 TO SPEND"]}
        reveals = seconds(scene, ws, 5.294)
        self.assertEqual(reveals, sorted(reveals))


class TestBigNumberAutoAnchor(unittest.TestCase):
    def test_d1_anchor_is_the_moment_the_number_is_said(self):
        ws = words(("That's", 0.0), ("$850", 0.33), ("a", 0.9), ("month", 1.0), ("of", 1.3), ("new", 1.4), ("spending,", 1.6))
        scene = {"sceneType": "big_number", "displayValue": "$850", "value": 850}
        out = sync.attach_reveals(scene, ws, 4.551)
        self.assertAlmostEqual(out["_anchor"] * 4.551, 0.33 - sync.LEAD_SECONDS, places=1)

    def test_number_split_across_tokens(self):
        ws = words(("Si", 0.0), ("tu", 0.2), ("gagnes", 0.4), ("3", 0.61), ("000", 0.77), ("dollars", 0.95))
        out = sync.attach_reveals({"sceneType": "big_number", "displayValue": "$3,000", "value": 3000}, ws, 4.18)
        self.assertAlmostEqual(out["_anchor"] * 4.18, 0.61 - sync.LEAD_SECONDS, places=1)

    def test_unspoken_number_is_left_alone(self):
        ws = words(("You", 0.0), ("got", 0.3), ("a", 0.5), ("raise.", 0.7))
        scene = {"sceneType": "big_number", "displayValue": "+$1,000", "value": 1000}
        self.assertIs(sync.attach_reveals(scene, ws, 2.136), scene)

    def test_written_voice_anchor_wins(self):
        ws = words(("monthly", 0.2), ("income", 0.5), ("is", 0.9), ("$3,000", 1.4))
        scene = {"sceneType": "big_number", "displayValue": "$3,000", "value": 3000, "voiceAnchor": "monthly income"}
        out = sync.attach_reveals(scene, ws, 4.0)
        self.assertAlmostEqual(out["_anchor"] * 4.0, 0.2 - sync.LEAD_SECONDS, places=1)

    def test_nothing_is_drawn_before_the_anchor(self):
        theme, size = resolve_theme(None), (270, 480)
        render = RENDERERS["big_number"]
        scene = {"sceneType": "big_number", "displayValue": "$850", "value": 850, "title": "NEW SPENDING"}
        anchored = {**scene, "_anchor": 0.4, "_duration": 4.0}
        titled = render({**scene, "displayValue": "", "value": None}, 0.2, theme, size).tobytes()
        self.assertEqual(render(anchored, 0.2, theme, size).tobytes(), titled)       # ni chiffre, ni ombre de chiffre
        self.assertNotEqual(render(anchored, 0.7, theme, size).tobytes(), titled)    # puis il apparait
        self.assertEqual(render(anchored, 1.0, theme, size).tobytes(), render(scene, 1.0, theme, size).tobytes())


class TestNoGhostBeforeTheVoice(unittest.TestCase):
    """Un element cale sur la voix n'est pas dessine avant son mot (un fondu parti de la couleur du fond laissait une
    ombre lisible du montant, de plus en plus longtemps avec des revelations tardives)."""

    SIZE = (270, 480)

    def _drawn_texts(self, scene, t):
        from engine.motion_graphics import layout
        theme = resolve_theme(None)
        with layout.record_boxes() as recorded:
            RENDERERS[scene["sceneType"]](scene, t, theme, self.SIZE)
        return " | ".join(r["text"] for r in recorded)

    def test_synced_items_are_absent_until_their_reveal(self):
        scene = {"sceneType": "compound_growth", "title": "Assumed 7%",
                 "data": [{"label": "Year 5", "displayValue": "$10,500"}, {"label": "Year 10", "displayValue": "$25,200"}],
                 "_reveals": [0.4, 0.7], "_duration": 7.0}
        self.assertNotIn("$10,500", self._drawn_texts(scene, 0.2))
        self.assertNotIn("$25,200", self._drawn_texts(scene, 0.2))
        self.assertIn("$10,500", self._drawn_texts(scene, 0.5))
        self.assertNotIn("$25,200", self._drawn_texts(scene, 0.5))
        self.assertIn("$25,200", self._drawn_texts(scene, 1.0))

    def test_every_list_scene_obeys_the_same_rule(self):
        scenes = [
            {"sceneType": "money_split", "data": [{"label": "A", "value": 1, "displayValue": "$11"}, {"label": "B", "value": 2, "displayValue": "$22"}]},
            {"sceneType": "bar_chart", "data": [{"label": "A", "value": 1, "displayValue": "$11"}, {"label": "B", "value": 2, "displayValue": "$22"}]},
            {"sceneType": "checklist", "items": ["First thing", "Second thing"]},
            {"sceneType": "formula", "terms": ["$11 FIRST", "= $22 SECOND"]},
            {"sceneType": "timeline", "steps": ["First step", "Second step"]},
        ]
        for scene in scenes:
            with self.subTest(scene=scene["sceneType"]):
                synced = {**scene, "_reveals": [0.6, 0.9], "_duration": 6.0}
                self.assertEqual(self._drawn_texts(synced, 0.1).count("|"), self._drawn_texts(synced, 0.0).count("|"))
                self.assertLess(len(self._drawn_texts(synced, 0.1)), len(self._drawn_texts(synced, 1.0)))

    def test_unsynced_scenes_keep_their_historical_rendering(self):
        scene = {"sceneType": "checklist", "items": ["First thing", "Second thing"]}
        self.assertIn("FIRST THING", self._drawn_texts(scene, 0.1).upper())


if __name__ == "__main__":
    unittest.main()
