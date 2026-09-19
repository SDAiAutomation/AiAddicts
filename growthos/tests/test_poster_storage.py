import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import poster, storage


class TestPosterArgs(unittest.TestCase):
    def test_extracts_a_single_scaled_frame(self):
        args = poster.build_poster_args("in.mp4", "out.jpg")
        self.assertEqual(args[0], "ffmpeg")
        self.assertIn("-frames:v", args)
        self.assertEqual(args[args.index("-frames:v") + 1], "1")
        self.assertIn(f"scale={poster.POSTER_WIDTH}:-2", args)
        self.assertLess(args.index("-ss"), args.index("-i"))  # seek rapide, avant l'entrée
        self.assertEqual(args[-1], "out.jpg")

    def test_empty_output_is_an_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "p.jpg")
            with patch.object(poster, "_run"):  # ffmpeg "réussit" sans rien écrire
                with self.assertRaises(RuntimeError):
                    poster.extract_poster("in.mp4", out)


class TestUpload(unittest.TestCase):
    def _client(self, public_url):
        client = MagicMock()
        bucket = client.storage.from_.return_value
        bucket.get_public_url.return_value = public_url
        return client, bucket

    def test_long_cache_and_versioned_url(self):
        client, bucket = self._client("https://x.test/storage/v1/object/public/content-videos/a.mp4")
        with patch.object(storage.time, "time", return_value=1234):
            url = storage.upload_video(client, "a", "/tmp/a.mp4")
        options = bucket.upload.call_args.kwargs["file_options"]
        self.assertEqual(options["cache-control"], "31536000")
        self.assertEqual(options["content-type"], "video/mp4")
        self.assertEqual(options["upsert"], "true")
        self.assertTrue(url.endswith("a.mp4?v=1234"))

    def test_existing_query_string_is_extended(self):
        client, _ = self._client("https://x.test/a.mp4?token=1")
        with patch.object(storage.time, "time", return_value=5):
            self.assertEqual(storage.upload_video(client, "a", "/tmp/a.mp4"), "https://x.test/a.mp4?token=1&v=5")

    def test_poster_is_a_jpeg_at_its_own_path(self):
        client, bucket = self._client("https://x.test/a.jpg")
        storage.upload_poster(client, "abc", "/tmp/p.jpg")
        self.assertEqual(bucket.upload.call_args.args[0], "abc.jpg")
        self.assertEqual(bucket.upload.call_args.kwargs["file_options"]["content-type"], "image/jpeg")


if __name__ == "__main__":
    unittest.main()
