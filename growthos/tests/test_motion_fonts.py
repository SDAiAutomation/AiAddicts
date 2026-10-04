import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw

from engine.motion_graphics import canvas, preflight, theme
from engine.motion_graphics.scenes import RENDERERS
from tests.test_motion_graphics import _SAMPLE_SCENES

SIZE = (1080, 1920)

# Longer, French, uppercase-heavy scenes: the hard case for a font wider than Poppins.
_LONG_SCENES = {
    "comparison_long": {
        "sceneType": "comparison", "title": "Livret A ou assurance-vie : lequel choisir pour votre épargne ?",
        "optionA": {"label": "Livret réglementé garanti par l'État", "displayValue": "3 % net d'impôt"},
        "optionB": {"label": "Assurance-vie en unités de compte diversifiée", "displayValue": "7 % brut annuel"},
    },
    "checklist_long": {
        "sceneType": "checklist", "title": "Les erreurs à éviter avant d'investir",
        "items": ["Rendement annuel moyen après frais et prélèvements sociaux sur la durée",
                  "Ne jamais investir l'argent dont vous aurez besoin dans l'année",
                  "Vérifier que le courtier est agréé par l'Autorité des marchés financiers"],
    },
    "bar_long": {
        "sceneType": "bar_chart", "title": "Répartition de l'épargne des ménages français",
        "data": [{"label": "Livrets réglementés et comptes", "value": 38}, {"label": "Assurance-vie en euros", "value": 29},
                 {"label": "Actions et fonds diversifiés", "value": 14}, {"label": "Immobilier locatif", "value": 19}],
    },
    "timeline_long": {
        "sceneType": "timeline", "title": "Votre plan d'épargne sur trente ans",
        "steps": ["Constituer une épargne de précaution", "Ouvrir un plan d'épargne retraite",
                  "Investir régulièrement chaque mois", "Réévaluer son allocation chaque année"],
    },
}

# Every accented letter and symbol the six generation languages (fr, en, es, de, it, pt) can need.
_COVERAGE = ("àâäæçéèêëîïôöœùûüÿÀÂÄÇÉÈÊËÎÏÔÖŒÙÛÜŸáíóúñãõÁÍÓÚÑÃÕìòÌÒß¿¡ªº"
             "€£$¥%+-×÷=<>·•…“”‘’«»–—°²³½()[]{}/&@#*:;,.!?0123456789")


def _themed(family):
    return theme.replace(theme.DEFAULT_THEME, font_family=family)


def _min_font(scene, family):
    return preflight.check_scene(scene, _themed(family), SIZE)["minFontPx"]


class TestFontFamilies(unittest.TestCase):
    def test_theme_and_canvas_know_the_same_families_and_their_files_exist(self):
        self.assertEqual(set(theme.FONT_FAMILIES), set(canvas._FONT_SPECS))
        for family, weights in canvas._FONT_SPECS.items():
            for bold, (path, _weight) in weights.items():
                self.assertTrue(Path(path).is_file(), f"{family} bold={bold}: {path}")

    def test_every_family_ships_its_licence(self):
        fonts = Path(__file__).parent.parent / "assets" / "fonts"
        for folder in ("ibm-plex-sans", "nunito"):
            self.assertTrue((fonts / folder / "OFL.txt").is_file(), folder)
        self.assertTrue((fonts / "OFL.txt").is_file())

    def test_presets_pick_a_known_family_and_classic_stays_on_poppins(self):
        for name, preset in theme.THEME_PRESETS.items():
            self.assertIn(preset.font_family, theme.FONT_FAMILIES, name)
        self.assertEqual(theme.DEFAULT_THEME.font_family, "poppins")
        self.assertEqual(theme.THEME_PRESETS["classic"].font_family, "poppins")
        self.assertEqual(theme.resolve_theme(None).font_family, "poppins")
        self.assertEqual(theme.THEME_PRESETS["trust_blue"].font_family, "ibm_plex_sans")
        self.assertEqual(theme.THEME_PRESETS["premium_indigo"].font_family, "ibm_plex_sans")
        self.assertEqual(theme.THEME_PRESETS["growth_green"].font_family, "nunito")

    def test_a_script_may_override_the_family_but_an_unknown_one_is_ignored(self):
        self.assertEqual(theme.resolve_theme({"preset": "classic", "font_family": "nunito"}).font_family, "nunito")
        self.assertEqual(theme.resolve_theme({"preset": "trust_blue", "font_family": "Comic Sans"}).font_family, "ibm_plex_sans")
        self.assertEqual(theme.resolve_theme({"font_family": "../../etc/passwd"}).font_family, "poppins")

    def test_the_active_family_selects_the_font_and_is_restored(self):
        self.assertEqual(canvas.font(40).getname()[0], "Poppins")
        with canvas.use_font_family("ibm_plex_sans"):
            self.assertEqual(canvas.font(40).getname()[0], "IBM Plex Sans")
            with canvas.use_font_family("nunito"):
                self.assertEqual(canvas.font(40).getname()[0], "Nunito")
            self.assertEqual(canvas.font(40).getname()[0], "IBM Plex Sans")
        self.assertEqual(canvas.font(40).getname()[0], "Poppins")

    def test_the_variable_font_is_pinned_to_regular_and_bold(self):
        probe = Image.new("RGB", (10, 10))
        draw = ImageDraw.Draw(probe)
        with canvas.use_font_family("nunito"):
            regular = draw.textlength("Épargne régulière", font=canvas.font(60, bold=False))
            bold = draw.textlength("Épargne régulière", font=canvas.font(60, bold=True))
        self.assertGreater(bold, regular)

    def test_an_unknown_family_or_a_missing_file_falls_back_to_poppins(self):
        with canvas.use_font_family("papyrus"):
            self.assertEqual(canvas.font(40).getname()[0], "Poppins")
        original = canvas._FONT_SPECS["nunito"]
        canvas._FONT_SPECS["nunito"] = {b: (Path("missing/Nunito.ttf"), w) for b, (_p, w) in original.items()}
        canvas._font.cache_clear()
        try:
            with canvas.use_font_family("nunito"):
                self.assertEqual(canvas.font(40).getname()[0], "Poppins")
        finally:
            canvas._FONT_SPECS["nunito"] = original
            canvas._font.cache_clear()

    def test_two_threads_rendering_different_themes_never_see_each_other(self):
        barrier = threading.Barrier(2)
        seen = {}

        def work(family):
            with canvas.use_font_family(family):
                barrier.wait()
                seen[family] = {canvas.font(40).getname()[0] for _ in range(200)}

        threads = [threading.Thread(target=work, args=(f,)) for f in ("ibm_plex_sans", "nunito")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(seen, {"ibm_plex_sans": {"IBM Plex Sans"}, "nunito": {"Nunito"}})

    def test_every_family_draws_every_character_the_six_languages_need(self):
        for family in theme.FONT_FAMILIES:
            with canvas.use_font_family(family):
                font = canvas.font(60)
            notdef = font.getmask("￿")
            notdef_bytes = bytes(notdef) if notdef.size != (0, 0) else b""
            missing = [c for c in _COVERAGE
                       if (lambda m: m.size == (0, 0) or bytes(m) == notdef_bytes)(font.getmask(c))]
            self.assertEqual(missing, [], family)


class TestFontsInScenes(unittest.TestCase):
    def test_classic_is_pixel_identical_to_the_historical_rendering(self):
        # Poppins for everything, exactly as before the font families existed.
        for kind, scene in _SAMPLE_SCENES.items():
            with self.subTest(kind=kind):
                implicit = RENDERERS[kind](scene, 0.7, theme.DEFAULT_THEME, SIZE)
                classic = RENDERERS[kind](scene, 0.7, theme.THEME_PRESETS["classic"], SIZE)
                with canvas.use_font_family("poppins"):
                    explicit = RENDERERS[kind](scene, 0.7, theme.DEFAULT_THEME, SIZE)
                self.assertEqual(implicit.tobytes(), classic.tobytes())
                self.assertEqual(implicit.tobytes(), explicit.tobytes())

    def test_a_non_classic_family_really_changes_the_pixels(self):
        scene = _SAMPLE_SCENES["big_number"]
        poppins = RENDERERS["big_number"](scene, 1.0, _themed("poppins"), SIZE)
        for family in ("ibm_plex_sans", "nunito"):
            self.assertNotEqual(poppins.tobytes(), RENDERERS["big_number"](scene, 1.0, _themed(family), SIZE).tobytes(), family)

    def test_the_font_does_not_leak_out_of_a_render(self):
        RENDERERS["big_number"](_SAMPLE_SCENES["big_number"], 1.0, _themed("nunito"), SIZE)
        self.assertEqual(canvas.font(40).getname()[0], "Poppins")

    def test_every_scene_passes_preflight_with_every_family(self):
        scenes = {**_SAMPLE_SCENES, **_LONG_SCENES}
        for family in theme.FONT_FAMILIES:
            for kind, scene in scenes.items():
                with self.subTest(family=family, scene=kind):
                    result = preflight.check_scene(scene, _themed(family), SIZE)
                    self.assertEqual(result["errors"], [])

    def test_no_family_forces_much_smaller_text_than_poppins(self):
        # Measured: Plex is 2-4 % and Nunito 6-8 % WIDER than Poppins in UPPERCASE (most labels), and
        # 6-8 % narrower in mixed case. Fitting adapts, so allow at most a 10 % smaller text.
        scenes = {**_SAMPLE_SCENES, **_LONG_SCENES}
        for family in ("ibm_plex_sans", "nunito"):
            for kind, scene in scenes.items():
                with self.subTest(family=family, scene=kind):
                    self.assertGreaterEqual(_min_font(scene, family), 0.9 * _min_font(scene, "poppins"))


if __name__ == "__main__":
    unittest.main()
