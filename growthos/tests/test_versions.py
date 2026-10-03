import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import storage, versions

ITEM = "8fb753ce-1111-2222-3333-444444444444"


class TestVersionedPaths(unittest.TestCase):
    def test_version_path_is_immutable_per_number(self):
        self.assertEqual(storage.version_path(ITEM, 3), f"{ITEM}/v3.mp4")
        self.assertEqual(storage.version_path(ITEM, 3, "srt"), f"{ITEM}/v3.srt")

    def test_is_versioned_url(self):
        self.assertTrue(storage.is_versioned_url(f"https://x.co/storage/v1/object/public/content-videos/{ITEM}/v2.mp4?v=1"))
        self.assertFalse(storage.is_versioned_url(f"https://x.co/content-videos/{ITEM}.mp4?v=1"))
        self.assertFalse(storage.is_versioned_url(None))

    def test_upload_video_uses_version_path_only_when_asked(self):
        client = MagicMock()
        client.storage.from_.return_value.get_public_url.return_value = "https://x.co/f"
        storage.upload_video(client, ITEM, __file__, version=2)
        self.assertEqual(client.storage.from_.return_value.upload.call_args[0][0], f"{ITEM}/v2.mp4")
        storage.upload_video(client, ITEM, __file__)
        self.assertEqual(client.storage.from_.return_value.upload.call_args[0][0], f"{ITEM}.mp4")


class TestVersionRecording(unittest.TestCase):
    def _client(self, last):
        client = MagicMock()
        chain = client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value.data = [{"version_number": last}] if last else []
        return client

    def test_first_and_next_number(self):
        self.assertEqual(versions.next_version_number(self._client(0), ITEM), 1)
        self.assertEqual(versions.next_version_number(self._client(4), ITEM), 5)

    def test_record_version_returns_id_and_never_raises(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "abc"}]
        self.assertEqual(versions.record_version(client, ITEM, 1, "generation", "u"), "abc")
        client.table.return_value.insert.return_value.execute.side_effect = RuntimeError("db down")
        self.assertIsNone(versions.record_version(client, ITEM, 2, "generation", "u"))

    def test_missing_srt_is_skipped(self):
        self.assertIsNone(versions.upload_captions_safe(MagicMock(), ITEM, 1, "does-not-exist.srt"))


if __name__ == "__main__":
    unittest.main()
