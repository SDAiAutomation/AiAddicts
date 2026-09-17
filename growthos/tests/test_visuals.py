import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import visuals


class TestMissingVisualFallback(unittest.TestCase):
    def test_reuses_nearest_successful_scene(self):
        self.assertEqual(
            visuals._fill_missing_visuals([None, "scene-2.jpg", None, None, "scene-5.jpg"]),
            ["scene-2.jpg", "scene-2.jpg", "scene-2.jpg", "scene-5.jpg", "scene-5.jpg"],
        )

    def test_keeps_empty_video_empty(self):
        self.assertEqual(visuals._fill_missing_visuals([None, None]), [None, None])


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


class TestShotPlanning(unittest.TestCase):
    def test_long_blocks_are_split_into_three_second_shots(self):
        from engine import video
        shots = video.plan_shots([7.5], ["scene.jpg"])
        self.assertEqual([s[2] for s in shots], [3.0, 3.0, 1.5])
        self.assertEqual([s[3] for s in shots], [0.0, 3.0, 6.0])
        self.assertAlmostEqual(sum(s[2] for s in shots), 7.5)

    def test_shots_keep_their_source_block(self):
        from engine import video
        shots = video.plan_shots([2.0, 4.0], ["a.jpg", "b.mp4"])
        self.assertEqual([(s[0], s[1]) for s in shots], [
            (1, "a.jpg"), (2, "b.mp4"), (2, "b.mp4")
        ])


if __name__ == "__main__":
    unittest.main()
