"""Durcissement de la source du rognage : origine, redirections, taille, validation du media."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import trim

BASE = "https://proj.supabase.co"
ITEM = "11111111-2222-4333-8444-555555555555"
OTHER = "99999999-2222-4333-8444-555555555555"
PREFIX = f"{BASE}/storage/v1/object/public/content-videos"


def trusted(url, item=ITEM):
    return trim.is_trusted_storage_url(url, item, BASE)


class TrustedStorageUrl(unittest.TestCase):
    def test_accepts_every_form_the_pipeline_writes(self):
        for url in (
            f"{PREFIX}/{ITEM}.mp4",
            f"{PREFIX}/{ITEM}.mp4?v=1790547166",  # cache-buster reel observe en production
            f"{PREFIX}/{ITEM}.mp4?t=1790547166",  # _bust()
            f"{PREFIX}/{ITEM}/v1.mp4",
            f"{PREFIX}/{ITEM}/v12.mp4?v=1791151171",
            f"{PREFIX}/{ITEM}.original.mp4",
            f"{BASE.upper()}/storage/v1/object/public/content-videos/{ITEM}.mp4".replace("HTTPS", "https"),
        ):
            self.assertTrue(trusted(url), url)

    def test_rejects_foreign_or_internal_hosts(self):
        for url in (
            f"https://evil.example/storage/v1/object/public/content-videos/{ITEM}.mp4",
            f"https://proj.supabase.co.evil.example/storage/v1/object/public/content-videos/{ITEM}.mp4",
            f"https://evil.example@proj.supabase.co/storage/v1/object/public/content-videos/{ITEM}.mp4",
            f"https://proj.supabase.co@evil.example/storage/v1/object/public/content-videos/{ITEM}.mp4",
            f"https://proj.supabase.co:8443/storage/v1/object/public/content-videos/{ITEM}.mp4",
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8080/x.mp4",
            "http://localhost/x.mp4",
            "http://[::1]/x.mp4",
            "file:///etc/passwd",
            "ftp://proj.supabase.co/x.mp4",
        ):
            self.assertFalse(trusted(url), url)

    def test_rejects_wrong_scheme_even_on_the_right_host(self):
        self.assertFalse(trusted(f"http://proj.supabase.co/storage/v1/object/public/content-videos/{ITEM}.mp4"))

    def test_rejects_paths_not_bound_to_this_content_item(self):
        for url in (
            f"{PREFIX}/{OTHER}.mp4",                       # la video d'un autre contenu
            f"{PREFIX}/{OTHER}/v1.mp4",
            f"{PREFIX}/{ITEM}/../{OTHER}.mp4",
            f"{PREFIX}/{ITEM}/%2e%2e/{OTHER}.mp4",
            f"{PREFIX}/{ITEM}/v1.mp4/extra",
            f"{PREFIX}/{ITEM}.mp4/",
            f"{PREFIX}/{ITEM}.mov",
            f"{PREFIX}/{ITEM}.mp4.exe",
            f"{PREFIX}/{ITEM}/v0.mp4",
            f"{PREFIX}/{ITEM}/v1234567.mp4",
            f"{BASE}/storage/v1/object/public/autre-bucket/{ITEM}.mp4",
            f"{BASE}/storage/v1/object/authenticated/content-videos/{ITEM}.mp4",
            f"{BASE}/storage/v1/object/sign/content-videos/{ITEM}.mp4?token=x",
            f"{BASE}/rest/v1/content_items",
        ):
            self.assertFalse(trusted(url), url)

    def test_rejects_unexpected_query_fragment_and_odd_characters(self):
        for url in (
            f"{PREFIX}/{ITEM}.mp4?token=abc",
            f"{PREFIX}/{ITEM}.mp4?v=1&x=2",
            f"{PREFIX}/{ITEM}.mp4?v=abc",
            f"{PREFIX}/{ITEM}.mp4#frag",
            f"{PREFIX}/{ITEM}.mp4\\..\\x",
            f"{PREFIX}/{ITEM}.mp4 ",
            f"{PREFIX}/{ITEM}.mp4\n",
            "",
            None,
        ):
            self.assertFalse(trusted(url), repr(url))

    def test_rejects_when_the_content_item_id_is_not_a_uuid(self):
        self.assertFalse(trim.is_trusted_storage_url(f"{PREFIX}/abc.mp4", "abc", BASE))
        self.assertFalse(trim.is_trusted_storage_url(f"{PREFIX}/.*.mp4", ".*", BASE))


def fake_response(status=200, chunks=(b"x" * 10,), headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.raise_for_status.side_effect = (lambda: None) if status < 400 else (lambda: (_ for _ in ()).throw(RuntimeError("http")))
    resp.iter_content.return_value = iter(chunks)
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


class Download(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "test-service-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tmp = Path(tempfile.mkdtemp())
        self.dest = self.tmp / "work" / "source.mp4"
        self.url = f"{PREFIX}/{ITEM}.mp4?v=1"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, **kw):
        return trim._download(self.url, self.dest, content_item_id=ITEM, supabase_url=BASE, **kw)

    def test_untrusted_url_is_refused_before_any_network_call(self):
        with patch("engine.trim.requests.get") as get:
            with self.assertRaises(ValueError):
                trim._download("http://169.254.169.254/latest/meta-data/", self.dest, content_item_id=ITEM, supabase_url=BASE)
            get.assert_not_called()
        self.assertFalse(self.dest.exists())

    def test_success_writes_the_file_and_never_follows_redirects(self):
        with patch("engine.trim.requests.get", return_value=fake_response(chunks=(b"abc", b"def"))) as get:
            self.call()
        self.assertEqual(self.dest.read_bytes(), b"abcdef")
        kwargs = get.call_args.kwargs
        self.assertIs(kwargs["allow_redirects"], False)
        self.assertTrue(kwargs["stream"])
        self.assertIsInstance(kwargs["timeout"], tuple)  # (connexion, lecture)
        self.assertIn("/object/authenticated/content-videos/", get.call_args.args[0])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-service-key")

    def test_missing_service_key_fails_closed(self):
        with patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": ""}), patch("engine.trim.requests.get") as get:
            with self.assertRaises(ValueError):
                self.call()
            get.assert_not_called()

    def test_redirect_is_refused_and_leaves_no_file(self):
        with patch("engine.trim.requests.get", return_value=fake_response(status=302, headers={"Location": "http://127.0.0.1/"})):
            with self.assertRaises(ValueError):
                self.call()
        self.assertFalse(self.dest.exists())

    def test_declared_size_over_the_cap_is_refused_without_reading_the_body(self):
        resp = fake_response(headers={"Content-Length": str(trim.MAX_DOWNLOAD_BYTES + 1)})
        with patch("engine.trim.requests.get", return_value=resp):
            with self.assertRaises(ValueError):
                self.call()
        resp.iter_content.assert_not_called()
        self.assertFalse(self.dest.exists())

    def test_stream_over_the_cap_without_content_length_is_cut_and_cleaned(self):
        big = (b"x" * 1024 for _ in range(10))
        with patch("engine.trim.MAX_DOWNLOAD_BYTES", 4096), \
             patch("engine.trim.requests.get", return_value=fake_response(chunks=big)):
            with self.assertRaises(ValueError):
                self.call()
        self.assertFalse(self.dest.exists())

    def test_total_time_budget_is_enforced(self):
        ticks = iter([0, 0, 1000, 1000, 1000])
        with patch("engine.trim.MAX_DOWNLOAD_SECONDS", 5), \
             patch("engine.trim.time.monotonic", side_effect=lambda: next(ticks)), \
             patch("engine.trim.requests.get", return_value=fake_response(chunks=(b"a", b"b", b"c"))):
            with self.assertRaises(ValueError):
                self.call()
        self.assertFalse(self.dest.exists())

    def test_http_error_cleans_up(self):
        with patch("engine.trim.requests.get", return_value=fake_response(status=500)):
            with self.assertRaises(Exception):
                self.call()
        self.assertFalse(self.dest.exists())

    def test_error_messages_are_generic(self):
        with patch("engine.trim.requests.get", return_value=fake_response(status=302, headers={"Location": "http://10.0.0.1/secret"})):
            with self.assertRaises(ValueError) as ctx:
                self.call()
        self.assertNotIn("10.0.0.1", str(ctx.exception))  # trim_error peut etre affiche a l'utilisateur
        with self.assertRaises(ValueError) as ctx:
            trim._download("http://10.0.0.1/secret", self.dest, content_item_id=ITEM, supabase_url=BASE)
        self.assertNotIn("10.0.0.1", str(ctx.exception))


def probe(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def probe_json(fmt="mov,mp4,m4a,3gp,3g2,mj2", duration="12.5", streams=({"codec_type": "video"}, {"codec_type": "audio"})):
    import json
    return probe(json.dumps({"format": {"format_name": fmt, "duration": duration}, "streams": list(streams)}))


class ValidateVideoFile(unittest.TestCase):
    def check(self, result):
        with patch("engine.trim.subprocess.run", return_value=result) as run:
            return trim.validate_video_file("source.mp4"), run

    def test_valid_mp4_passes_and_ffprobe_cannot_open_network_protocols(self):
        _, run = self.check(probe_json())
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0], "ffprobe")
        self.assertEqual(cmd[cmd.index("-protocol_whitelist") + 1], "file")
        self.assertLess(cmd.index("-protocol_whitelist"), len(cmd) - 1)

    def test_rejects_non_mp4_containers_such_as_playlists(self):
        for fmt in ("hls", "mpegts", "matroska,webm", "concat", "ffmetadata"):
            with self.assertRaises(ValueError, msg=fmt):
                self.check(probe_json(fmt=fmt))

    def test_rejects_missing_video_stream_and_bad_durations(self):
        with self.assertRaises(ValueError):
            self.check(probe_json(streams=({"codec_type": "audio"},)))
        for d in ("0", "0.1", "-3", "N/A", "99999"):
            with self.assertRaises(ValueError, msg=d):
                self.check(probe_json(duration=d))

    def test_rejects_unreadable_file_and_probe_failures(self):
        with self.assertRaises(ValueError):
            self.check(probe(returncode=1))
        with self.assertRaises(ValueError):
            self.check(probe("not json"))
        with patch("engine.trim.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 30)):
            with self.assertRaises(ValueError):
                trim.validate_video_file("source.mp4")
        with patch("engine.trim.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(ValueError):
                trim.validate_video_file("source.mp4")


@unittest.skipUnless(shutil.which("ffprobe") and shutil.which("ffmpeg"), "ffmpeg/ffprobe absents")
class ValidateVideoFileWithRealFfprobe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_real_mp4_is_accepted(self):
        path = self.tmp / "ok.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1:r=10",
                        "-f", "lavfi", "-i", "sine=f=440:d=1", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", str(path)], check=True, capture_output=True)
        trim.validate_video_file(path)

    def test_hls_playlist_pointing_to_a_remote_url_is_rejected(self):
        playlist = self.tmp / "evil.mp4"
        playlist.write_text("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:9/x.ts\n#EXT-X-ENDLIST\n")
        with self.assertRaises(ValueError):
            trim.validate_video_file(playlist)

    def test_text_file_and_html_are_rejected(self):
        for name, body in (("a.mp4", "hello"), ("b.mp4", "<html><body>secret</body></html>")):
            path = self.tmp / name
            path.write_text(body)
            with self.assertRaises(ValueError, msg=name):
                trim.validate_video_file(path)


class ApplyTrimRefusesBeforeAnyUpload(unittest.TestCase):
    def run_apply(self, item, download=None, validate=None):
        client = MagicMock()
        with patch("engine.trim.storage") as storage, \
             patch("engine.trim._download", side_effect=download or (lambda *a, **k: None)) as dl, \
             patch("engine.trim.validate_video_file", side_effect=validate or (lambda *a, **k: None)) as val, \
             patch("engine.trim._run") as run, \
             patch("engine.trim.versions"), patch("engine.trim.poster"):
            storage.is_versioned_url.return_value = True
            try:
                trim.apply_trim(client, item, output_root=tempfile.mkdtemp())
                outcome = None
            except Exception as exc:  # noqa: BLE001
                outcome = exc
            return outcome, storage, dl, val, run

    def item(self, **over):
        base = {"id": ITEM, "video_url": f"{PREFIX}/{ITEM}/v1.mp4", "original_video_url": None, "trim_start": 1, "trim_end": 5}
        base.update(over)
        return base

    def test_download_receives_the_content_item_id_so_the_path_is_bound_to_it(self):
        _, _, dl, _, _ = self.run_apply(self.item())
        self.assertEqual(dl.call_args.kwargs.get("content_item_id"), ITEM)

    def test_untrusted_source_never_reaches_upload_or_ffmpeg(self):
        def refuse(*a, **k):
            raise ValueError("Source video non autorisee.")
        outcome, storage, _, val, run = self.run_apply(self.item(original_video_url="http://169.254.169.254/x"), download=refuse)
        self.assertIsInstance(outcome, ValueError)
        storage.upload_video.assert_not_called()
        storage.upload_original.assert_not_called()
        val.assert_not_called()
        run.assert_not_called()

    def test_invalid_media_never_reaches_upload_or_ffmpeg(self):
        def bad(*a, **k):
            raise ValueError("Source video invalide.")
        outcome, storage, _, _, run = self.run_apply(self.item(trim_start=0, trim_end=None), validate=bad)
        self.assertIsInstance(outcome, ValueError)
        storage.upload_video.assert_not_called()  # y compris la branche « retablir la version complete »
        run.assert_not_called()

    def test_validation_runs_after_download_and_before_anything_else(self):
        order = []
        self.run_apply(self.item(), download=lambda *a, **k: order.append("download"), validate=lambda *a, **k: order.append("validate"))
        self.assertEqual(order[:2], ["download", "validate"])


class TrimArgsCannotOpenNetworkProtocols(unittest.TestCase):
    def test_ffmpeg_input_is_limited_to_local_files(self):
        args = trim.build_trim_args("in.mp4", "out.mp4", 2.0, 10.0)
        self.assertEqual(args[args.index("-protocol_whitelist") + 1], "file")
        self.assertLess(args.index("-protocol_whitelist"), args.index("-i"))  # option d'entree : avant -i


if __name__ == "__main__":
    unittest.main()
