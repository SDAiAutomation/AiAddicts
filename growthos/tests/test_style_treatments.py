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
