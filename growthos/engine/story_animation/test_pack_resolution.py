"""Which pack a look is printed from, and where it lives under STORY_PACK_DIR."""
import tempfile
import unittest
from pathlib import Path

from growthos.engine.story_animation import packs, pipeline


class PackResolution(unittest.TestCase):
    def test_tinted_looks_use_the_base_pack_and_colour_has_its_own(self):
        for style in (None, "", "noir_1930", "sepia_1930", "cyanotype_1930"):
            self.assertEqual(packs.pack_id_for_style(style), packs.BASE_PACK)
        self.assertEqual(packs.pack_id_for_style("couleur_1930"), "couleur_v1")

    def test_every_look_of_the_catalog_resolves_to_a_known_pack(self):
        for style in pipeline.STYLES:
            self.assertIn(packs.pack_id_for_style(style), {packs.BASE_PACK, *packs.STYLE_PACKS.values()})

    def test_one_folder_per_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(packs.resolve_pack_dir(root, "noir_1930"), root / "prototype_v1")
            self.assertEqual(packs.resolve_pack_dir(root, "couleur_1930"), root / "couleur_v1")

    def test_a_root_that_is_itself_the_base_pack_still_works_for_the_base_pack_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bg_shop.png").write_bytes(b"x")
            self.assertEqual(packs.resolve_pack_dir(root, "sepia_1930"), root)
            self.assertEqual(packs.resolve_pack_dir(root, "couleur_1930"), root / "couleur_v1")  # never the wrong pack

    def test_an_unknown_style_cannot_pick_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(packs.resolve_pack_dir(tmp, "../../etc"), Path(tmp) / packs.BASE_PACK)

    def test_the_worker_workflow_fetches_every_pack_a_look_can_use(self):
        workflow = (Path(__file__).resolve().parents[3] / ".github" / "workflows" / "story-animation-worker.yml").read_text(encoding="utf-8")
        for pack in {packs.BASE_PACK, *packs.STYLE_PACKS.values()}:
            self.assertIn(pack, workflow)
        self.assertIn("story-packs\n", workflow.replace("\r\n", "\n"))


if __name__ == "__main__":
    unittest.main()
