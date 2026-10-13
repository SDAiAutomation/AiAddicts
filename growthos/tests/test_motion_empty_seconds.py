"""Scenes Motion Graphics : pas de seconde vide evitable avant la 1re revelation."""
import unittest

from engine.motion_graphics import sync
from engine.motion_graphics.theme import DEFAULT_THEME, THEME_PRESETS

# Voix : « emergency cushion » n'est dit qu'a 3,2 s ; « two hundred » (le montant) a 3,6 s.
WORDS = [{"text": "Step", "start": 0.2}, {"text": "one", "start": 0.6}, {"text": "set", "start": 1.4},
         {"text": "aside", "start": 2.0}, {"text": "emergency", "start": 3.2}, {"text": "cushion", "start": 3.4},
         {"text": "200", "start": 3.6}, {"text": "debt", "start": 5.0}, {"text": "100", "start": 5.4}]
DURATION = 8.0


class TestFirstItemDelay(unittest.TestCase):
    def test_label_only_first_item_appears_within_the_cap(self):
        scene = {"sceneType": "checklist", "items": ["Emergency cushion", "Debt"]}
        reveals = sync.compute_reveals(scene, WORDS, DURATION)
        self.assertLessEqual(reveals[0] * DURATION, sync.FIRST_ITEM_MAX_DELAY_SECONDS + 1e-3)
        self.assertEqual(reveals, sorted(reveals))  # ordre monotone conserve

    def test_numeric_first_item_is_never_shown_before_its_number_is_spoken(self):
        scene = {"sceneType": "money_split", "data": [
            {"label": "Emergency", "value": 200, "displayValue": "$200"},
            {"label": "Debt", "value": 100, "displayValue": "$100"}]}
        reveals = sync.compute_reveals(scene, WORDS, DURATION)
        self.assertGreaterEqual(reveals[0] * DURATION, 3.6 - sync.LEAD_SECONDS - 1e-3)


class TestTitleContrast(unittest.TestCase):
    @staticmethod
    def _lum(rgb):
        f = lambda v: v / 255 / 12.92 if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])

    def test_scene_title_reaches_readable_contrast_on_every_preset(self):
        from engine.motion_graphics.theme import lerp_color
        for name, theme in THEME_PRESETS.items():
            mixed = lerp_color(theme.secondary, theme.text, 0.5)
            bg = lerp_color(theme.background, theme.background, 0)
            ratio = (self._lum(mixed) + 0.05) / (self._lum(bg) + 0.05)
            self.assertGreaterEqual(ratio, 7.0, name)


if __name__ == "__main__":
    unittest.main()
