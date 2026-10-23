import unittest

from engine import assembler


class BlockVoiceTests(unittest.TestCase):
    def test_story_block_voice_overrides_default(self):
        data = {"content_format": "story"}
        self.assertEqual(assembler.block_voice_id(data, {"voice_id": " v2 "}, "v1"), "v2")

    def test_story_block_without_voice_uses_default(self):
        for block in ({}, {"voice_id": ""}, {"voice_id": "  "}, {"voice_id": None}, {"voice_id": 5}):
            self.assertEqual(assembler.block_voice_id({"content_format": "story"}, block, "v1"), "v1")

    def test_other_formats_ignore_block_voice(self):
        for fmt in ("standard", "quiz", None):
            data = {"content_format": fmt} if fmt else {}
            self.assertEqual(assembler.block_voice_id(data, {"voice_id": "forged"}, "v1"), "v1")


if __name__ == "__main__":
    unittest.main()
