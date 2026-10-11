import os
import unittest
from unittest.mock import Mock, patch
from engine.assembler import _store_creative_quality_shadow

class ShadowIntegrationTests(unittest.TestCase):
    def test_disabled_does_not_query_database(self):
        client = Mock()
        with patch.dict(os.environ, {"CREATIVE_QUALITY_PERSIST_ENABLED": "false"}):
            _store_creative_quality_shadow(client, "item", {"blocks":[]}, {}, "video.mp4", "v1")
        client.table.assert_not_called()

    def test_missing_expected_version_does_not_query_database(self):
        client = Mock()
        with patch.dict(os.environ, {"CREATIVE_QUALITY_PERSIST_ENABLED": "true"}):
            _store_creative_quality_shadow(client, "item", {"blocks":[]}, {}, "video.mp4", None)
        client.table.assert_not_called()

    def test_stale_version_skips_writer(self):
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "script_version": 1, "video_script_version": 1, "current_version_id": "newer"
        }
        with patch.dict(os.environ, {"CREATIVE_QUALITY_PERSIST_ENABLED": "true"}):
            with patch("engine.creative_quality_writer.store_report") as writer:
                _store_creative_quality_shadow(client, "item", {"blocks":[]}, {}, "video.mp4", "older")
                writer.assert_not_called()

if __name__ == "__main__":
    unittest.main()
