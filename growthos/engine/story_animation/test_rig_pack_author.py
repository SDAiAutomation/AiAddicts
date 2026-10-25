"""Offline safeguards for generated cutout art before Godot sees it."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from growthos.engine.story_animation import demo_rig_v2, rig_manifest, rig_pack_author


class RigPackAuthorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        _, pack = demo_rig_v2.create(self.root / "demo", 12)
        self.source = pack / "tavi_owl"
        original = json.loads((self.source / "rig.json").read_text(encoding="utf-8"))
        self.layout = {key: original[key] for key in ("character_id", "canvas", "anchors", "face")}

    def test_reviewed_rgba_parts_form_a_loadable_pack(self):
        target = self.root / "approved" / "tavi_owl"
        manifest = rig_pack_author.author_pack(self.source, self.layout, target)
        self.assertEqual(manifest["character_id"], "tavi_owl")
        self.assertEqual(rig_manifest.load_manifest(target / "rig.json", target), manifest)
        with self.assertRaises(rig_pack_author.ArtIntakeError):
            rig_pack_author.author_pack(self.source, self.layout, target)

    def test_opaque_generated_png_is_rejected_before_pack_creation(self):
        changed = self.root / "changed"
        changed.mkdir()
        for role in rig_manifest.SPRITES:
            (changed / f"{role}.png").write_bytes((self.source / f"{role}.png").read_bytes())
        Image.new("RGB", (100, 100), "white").save(changed / "head.png")
        target = self.root / "bad"
        with self.assertRaisesRegex(rig_pack_author.ArtIntakeError, "transparent RGBA"):
            rig_pack_author.author_pack(changed, self.layout, target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
