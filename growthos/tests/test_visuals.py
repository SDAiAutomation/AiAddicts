import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import visuals


class TestGroupBlocks(unittest.TestCase):
    def test_groups_of_three(self):
        self.assertEqual(visuals._group_blocks(7, 3), [[0, 1, 2], [3, 4, 5], [6]])

    def test_groups_of_one_is_one_per_block(self):
        self.assertEqual(visuals._group_blocks(4, 1), [[0], [1], [2], [3]])

    def test_default_blocks_per_image_is_one(self):
        # une image par bloc par défaut (VISUALS_BLOCKS_PER_IMAGE non défini)
        self.assertEqual(visuals._BLOCKS_PER_IMAGE, 1)


class TestPrefersStockFootage(unittest.TestCase):
    def test_true_for_known_ids(self):
        self.assertTrue(visuals.prefers_stock_footage("stock_footage", ""))
        self.assertTrue(visuals.prefers_stock_footage("stock_video", ""))

    def test_true_for_phrase_mentioning_stock_footage(self):
        self.assertTrue(visuals.prefers_stock_footage("", "clips en stock footage, lumière naturelle"))
        self.assertTrue(visuals.prefers_stock_footage("", "vidéo de stock réaliste"))

    def test_false_for_illustrated_styles(self):
        self.assertFalse(visuals.prefers_stock_footage("storybook", "illustration album jeunesse"))
        self.assertFalse(visuals.prefers_stock_footage("anime", ""))
        self.assertFalse(visuals.prefers_stock_footage("", ""))

    def test_false_for_plain_realistic_photo_style(self):
        # "photographie réaliste" seul ne bascule PAS en vidéo (c'est le style
        # par défaut du prompt IA quand il n'y a pas de fiche personnage)
        self.assertFalse(
            visuals.prefers_stock_footage("cinematic_real", "photo cinématique réaliste, objectif 35mm")
        )


class TestVideoExtDetection(unittest.TestCase):
    def test_video_module_recognises_mp4(self):
        from engine import video
        self.assertTrue("captions.ass".lower().endswith(video._VIDEO_EXTS) is False)
        self.assertTrue("block-01.mp4".lower().endswith(video._VIDEO_EXTS))
        self.assertFalse("scene-01.jpg".lower().endswith(video._VIDEO_EXTS))


class TestKenBurnsMoves(unittest.TestCase):
    def test_move_cycles_by_block_index(self):
        from engine import video
        moves = [video._KB_MOVES[(i - 1) % len(video._KB_MOVES)] for i in range(1, 9)]
        self.assertEqual(moves[0], "in")
        self.assertEqual(moves[1], "out")
        self.assertEqual(moves[6], "in")  # boucle après 6

    def test_filter_string_per_move(self):
        from engine import video
        for move in video._KB_MOVES:
            vf = video._kenburns_filter(move, "1080x1920", 100, 25)
            self.assertIn("zoompan=", vf)
            self.assertIn("s=1080x1920", vf)
        self.assertIn("(iw-iw/zoom)*on/100", video._kenburns_filter("right", "1080x1920", 100, 25))
        self.assertIn("1.28-0.0016*on", video._kenburns_filter("out", "1080x1920", 100, 25))


if __name__ == "__main__":
    unittest.main()
