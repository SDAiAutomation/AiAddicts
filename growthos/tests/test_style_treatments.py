"""Phase 3 (distinctive style engines) — comic_book / gta_loading (Game
Loading Screen) compositing treatments. Pure Pillow, no network, no AI call:
these tests generate small synthetic source images on disk and assert on the
treated output."""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import style_treatments
from engine.style_treatments import comic, game_art
from engine.style_treatments._shared import safe_margin


def _has_color_near(img: Image.Image, color, box, tolerance=24) -> bool:
    for pixel in img.crop(box).getdata():
        if all(abs(pixel[i] - color[i]) <= tolerance for i in range(3)):
            return True
    return False


def _make_source(path: Path, size=(600, 900)) -> str:
    img = Image.new("RGB", size, (120, 140, 200))
    img.save(path, "JPEG", quality=90)
    return str(path)


class TestComicLayoutSelection(unittest.TestCase):
    def test_wide_shot_is_full_panel(self):
        self.assertEqual(comic.select_layout("wide", "establish"), "FULL_PANEL")

    def test_reveal_purpose_is_always_full_panel(self):
        self.assertEqual(comic.select_layout("close_up", "reveal"), "FULL_PANEL")
        self.assertEqual(comic.select_layout("medium", "payoff"), "FULL_PANEL")

    def test_insert_shot_is_inset_panel(self):
        self.assertEqual(comic.select_layout("insert", "evidence"), "INSET_PANEL")

    def test_medium_action_is_split_horizontal(self):
        self.assertEqual(comic.select_layout("medium", "action"), "SPLIT_HORIZONTAL")

    def test_close_up_defaults_to_single_panel(self):
        self.assertEqual(comic.select_layout("close_up", "reaction"), "SINGLE_PANEL")

    def test_unknown_shot_type_defaults_to_single_panel(self):
        self.assertEqual(comic.select_layout(None, None), "SINGLE_PANEL")

    def test_layout_selection_is_deterministic(self):
        for _ in range(5):
            self.assertEqual(comic.select_layout("insert", "evidence"), "INSET_PANEL")


class TestComicApply(unittest.TestCase):
    def test_treatment_produces_a_valid_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg")
            out = str(Path(tmp) / "scene-01.treated.jpg")
            metadata = comic.apply(src, out, "wide", "establish")
            self.assertTrue(Path(out).exists())
            with Image.open(out) as img:
                self.assertEqual(img.size, (600, 900))
            self.assertEqual(metadata["styleTreatment"], "comic")
            self.assertEqual(metadata["layout"], "FULL_PANEL")
            self.assertTrue(metadata["treatmentApplied"])

    def test_original_asset_is_never_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "scene-01.jpg"
            _make_source(src)
            original_bytes = src.read_bytes()
            comic.apply(str(src), str(Path(tmp) / "scene-01.treated.jpg"), "insert", "evidence")
            self.assertEqual(src.read_bytes(), original_bytes)

    def test_insert_shot_treatment_applies_inset_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg")
            metadata = comic.apply(src, str(Path(tmp) / "out.jpg"), "insert", "evidence")
            self.assertEqual(metadata["layout"], "INSET_PANEL")

    def test_reveal_payoff_behaviour_is_full_panel_regardless_of_shot_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg")
            metadata = comic.apply(src, str(Path(tmp) / "out.jpg"), "close_up", "payoff")
            self.assertEqual(metadata["layout"], "FULL_PANEL")

    def test_reused_fallback_image_still_gets_treated(self):
        """Section 13 of the Phase 3 brief: a block that reuses a neighbour's
        source image must still get ITS OWN treatment (own shotType), not
        skip treatment because the source file came from elsewhere."""
        with tempfile.TemporaryDirectory() as tmp:
            shared_source = _make_source(Path(tmp) / "scene-02.jpg")
            metadata = comic.apply(shared_source, str(Path(tmp) / "scene-05.treated.jpg"), "insert", "evidence")
            self.assertTrue(metadata["treatmentApplied"])
            self.assertEqual(metadata["layout"], "INSET_PANEL")


class TestGameArtWantsLoadingMotif(unittest.TestCase):
    def test_hook_and_establish_get_the_motif(self):
        self.assertTrue(game_art.wants_loading_motif("wide", "hook"))
        self.assertTrue(game_art.wants_loading_motif("medium", "establish"))

    def test_normal_action_does_not_get_the_motif(self):
        self.assertFalse(game_art.wants_loading_motif("medium", "action"))
        self.assertFalse(game_art.wants_loading_motif("close_up", "reaction"))

    def test_rule_is_deterministic(self):
        for _ in range(5):
            self.assertTrue(game_art.wants_loading_motif("wide", "hook"))


class TestComicBorderSafeMargin(unittest.TestCase):
    """Regression (Phase 3 final-video QA) : une bordure dessinée flush
    contre le bord était intégralement rognée par le crop d'aspect ratio +
    Ken Burns du pipeline de rendu final (engine/video.py) — confirmé
    invisible sur une vraie vidéo rendue. Doit être tracée à `safe_margin()`
    du bord, jamais à 0."""

    def test_full_panel_border_is_inset_not_at_the_raw_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg", size=(1024, 1536))
            out = Path(tmp) / "out.jpg"
            comic.apply(str(src), str(out), "wide", "establish")
            with Image.open(out) as treated:
                w, h = treated.size
                margin = safe_margin((w, h))
                self.assertFalse(_has_color_near(treated, comic._INK_COLOR, (0, 0, w, 4)))
                self.assertFalse(_has_color_near(treated, comic._INK_COLOR, (0, 0, 4, h)))
                band = (0, margin - 3, w, margin + 3)
                self.assertTrue(_has_color_near(treated, comic._INK_COLOR, band))


class TestGameArtFrameSafeMargin(unittest.TestCase):
    """Regression (Phase 3 final-video QA), même défaut que le comic :
    cadre décoratif et motif LOADING flush contre le bord étaient rognés par
    le pipeline de rendu final (confirmé : le "L" de "LOADING" et le début
    de la barre de progression étaient hors-cadre sur une vraie vidéo)."""

    def test_frame_is_inset_not_at_the_raw_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg", size=(1024, 1536))
            out = Path(tmp) / "out.jpg"
            game_art.apply(str(src), str(out), "wide", "establish")
            with Image.open(out) as treated:
                w, h = treated.size
                margin = safe_margin((w, h))
                self.assertFalse(_has_color_near(treated, game_art._FRAME_COLOR, (0, 0, w, 4)))
                band = (0, margin - 4, w, margin + 4)
                self.assertTrue(_has_color_near(treated, game_art._FRAME_COLOR, band))

    def test_loading_motif_label_is_not_clipped_at_the_left_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg", size=(1024, 1536))
            out = Path(tmp) / "out.jpg"
            game_art.apply(str(src), str(out), "wide", "hook")
            with Image.open(out) as treated:
                w, h = treated.size
                margin = safe_margin((w, h))
                self.assertFalse(
                    _has_color_near(treated, game_art._FRAME_COLOR, (0, 0, margin - 5, h))
                )


class TestGameArtVignette(unittest.TestCase):
    """Regression (Phase 3 visual QA) : une 1re version assombrissait le
    CENTRE et éclaircissait les COINS — l'inverse d'une vignette — confirmé
    en comparant la luminosité moyenne coin/centre sur une vraie image de
    scène avant/après traitement. Corrigé dans `_vignette()`."""

    def test_corners_are_darker_than_center_after_vignette(self):
        # Image source unie : toute différence coin/centre après traitement
        # vient UNIQUEMENT de la vignette, jamais du contenu de l'image.
        flat = Image.new("RGB", (400, 600), (180, 180, 180))
        treated = game_art._vignette(flat)
        w, h = treated.size

        def avg_luma(box):
            pixels = list(treated.crop(box).getdata())
            return sum(sum(p) for p in pixels) / (len(pixels) * 3)

        corner = avg_luma((0, 0, 40, 40))
        center = avg_luma((w // 2 - 20, h // 2 - 20, w // 2 + 20, h // 2 + 20))
        self.assertLess(corner, center)
        self.assertLess(corner, 180)  # le coin doit être assombri par rapport à l'original
        self.assertGreater(center, corner + 20)  # écart net, pas un artefact d'arrondi


class TestGameArtApply(unittest.TestCase):
    def test_treatment_produces_a_valid_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg")
            out = str(Path(tmp) / "scene-01.treated.jpg")
            metadata = game_art.apply(src, out, "wide", "hook")
            self.assertTrue(Path(out).exists())
            with Image.open(out) as img:
                self.assertEqual(img.size, (600, 900))
            self.assertEqual(metadata["styleTreatment"], "game_art")
            self.assertTrue(metadata["treatmentApplied"])
            self.assertTrue(metadata["loadingMotif"])

    def test_original_asset_is_never_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "scene-01.jpg"
            _make_source(src)
            original_bytes = src.read_bytes()
            game_art.apply(str(src), str(Path(tmp) / "out.jpg"), "medium", "action")
            self.assertEqual(src.read_bytes(), original_bytes)

    def test_action_shot_has_no_loading_motif(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg")
            metadata = game_art.apply(src, str(Path(tmp) / "out.jpg"), "medium", "action")
            self.assertFalse(metadata["loadingMotif"])


class TestTreatmentRegistry(unittest.TestCase):
    def test_comic_and_game_loading_are_registered(self):
        self.assertTrue(style_treatments.has_treatment("comic_book"))
        self.assertTrue(style_treatments.has_treatment("gta_loading"))

    def test_legacy_gta_loading_id_resolves_correctly(self):
        # `gta_loading` est l'id INTERNE historique (voir image_style_bible) —
        # doit continuer de résoudre au treatment "Game Loading Screen".
        with tempfile.TemporaryDirectory() as tmp:
            src = _make_source(Path(tmp) / "scene-01.jpg")
            metadata = style_treatments.apply_treatment("gta_loading", src, str(Path(tmp) / "out.jpg"), "wide", "hook")
            self.assertEqual(metadata["styleTreatment"], "game_art")

    def test_other_styles_have_no_treatment(self):
        for style_id in ("cinematic_real", "anime", "storybook", "pixar_3d", "motion_graphics", "flat_color", "stock_footage"):
            self.assertFalse(style_treatments.has_treatment(style_id), style_id)
        self.assertIsNone(style_treatments.apply_treatment("anime", "a.jpg", "b.jpg", "wide", "hook"))


if __name__ == "__main__":
    unittest.main()
