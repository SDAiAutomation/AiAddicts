import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from growthos.engine.story_animation import cli, packs, rig_v1
from growthos.engine.story_animation.renderer import RenderError

FIXTURES = Path(__file__).parent / "fixtures"


def timeline():
    return json.loads((FIXTURES / "prototype_timeline.json").read_text(encoding="utf-8"))


class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pack = Path(self.tmp.name) / "pack"
        packs.write_placeholder_pack(self.pack)

    def tearDown(self):
        self.tmp.cleanup()

    def test_placeholder_pack_is_valid(self):
        self.assertEqual(packs.validate_pack(self.pack), [])
        self.assertEqual(len(list(self.pack.glob("*.png"))), len(packs.REQUIRED_SPRITES))

    def test_missing_file(self):
        (self.pack / "torso.png").unlink()
        self.assertTrue(any("torso.png is missing" in p for p in packs.validate_pack(self.pack)))

    def test_wrong_size(self):
        packs._write_png(self.pack / "hat.png", 10, 10, (0, 0, 0, 255))
        self.assertTrue(any("hat.png is 10x10" in p for p in packs.validate_pack(self.pack)))

    def test_not_a_png(self):
        (self.pack / "clock.png").write_bytes(b"MZ not an image at all, just text padding.")
        self.assertTrue(any("not a PNG" in p for p in packs.validate_pack(self.pack)))

    def test_missing_directory(self):
        self.assertTrue(packs.validate_pack(Path(self.tmp.name) / "nope"))

    def test_symlink_is_refused(self):
        target = self.pack / "real.png"
        (self.pack / "hat.png").rename(target)
        try:
            os.symlink(target, self.pack / "hat.png")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this machine")
        self.assertTrue(any("symbolic link" in p for p in packs.validate_pack(self.pack)))


class HelperTests(unittest.TestCase):
    def test_clean_env_removes_secrets(self):
        env = {"PATH": "/bin", "OPENAI_API_KEY": "x", "ELEVENLABS_API_KEY": "y", "SUPABASE_SERVICE_ROLE_KEY": "z", "GITHUB_TOKEN": "t", "HOME": "/h", "DB_PASSWORD": "p"}
        self.assertEqual(rig_v1.clean_env(env), {"PATH": "/bin", "HOME": "/h"})

    def test_confine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(rig_v1.confine(root / "a.json", root), (root / "a.json").resolve())
            with self.assertRaises(RenderError):
                rig_v1.confine(root / ".." / "evil", root)
            with self.assertRaises(RenderError):
                rig_v1.confine(Path(tmp).parent / "other", root)

    def test_estimate(self):
        est = rig_v1.RigV1Renderer("godot").estimate(20.0, 400)
        self.assertEqual((est.render_seconds, est.tts_chars, est.provider_calls, est.estimated), (120.0, 400, 0, True))
        for args in ((0, 10), (-1, 10), (float("nan"), 10), (10, -1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                rig_v1.RigV1Renderer("godot").estimate(*args)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pack = self.root / "pack"
        packs.write_placeholder_pack(self.pack)
        self.work = self.root / "job"

    def tearDown(self):
        self.tmp.cleanup()

    def fake_run(self, godot_code=0, ffmpeg_code=0):
        calls = []

        def run(cmd, timeout_s, env):
            calls.append((cmd, timeout_s, env))
            if "--write-movie" in cmd:
                if godot_code == 0:
                    Path(cmd[cmd.index("--write-movie") + 1]).write_bytes(b"avi")
                return subprocess.CompletedProcess(cmd, godot_code, "", "ERROR: boom" if godot_code else "")
            if ffmpeg_code == 0:
                Path(cmd[-1]).write_bytes(b"mp4")
            return subprocess.CompletedProcess(cmd, ffmpeg_code, "", "")
        return run, calls

    def test_success_builds_a_safe_command(self):
        run, calls = self.fake_run()
        with mock.patch.object(rig_v1, "_run", run), mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-secret", "PATH": "/bin"}):
            result = rig_v1.RigV1Renderer("/opt/godot", launcher=("xvfb-run", "-a")).render(timeline(), self.pack, self.work, 120)
        godot_cmd, timeout, env = calls[0]
        self.assertEqual(godot_cmd[:3], ["xvfb-run", "-a", "/opt/godot"])
        self.assertIn("--write-movie", godot_cmd)
        self.assertIn(f"--pack={self.pack.resolve()}", godot_cmd)
        self.assertEqual(godot_cmd[godot_cmd.index("--fixed-fps") + 1], "24")
        self.assertEqual(timeout, 120)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertTrue(all(isinstance(part, str) for part in godot_cmd))
        self.assertTrue((self.work / "timeline.json").is_file())
        self.assertEqual((result.width, result.height, result.fps, result.frames), (1080, 1920, 24, 518))
        self.assertTrue(result.video_path.is_file())

    def test_renderer_failure_is_reported_without_a_video(self):
        run, _ = self.fake_run(godot_code=3)
        with mock.patch.object(rig_v1, "_run", run), self.assertRaises(RenderError) as ctx:
            rig_v1.RigV1Renderer("godot").render(timeline(), self.pack, self.work)
        self.assertIn("exit code 3", str(ctx.exception))

    def test_encoding_failure(self):
        run, _ = self.fake_run(ffmpeg_code=1)
        with mock.patch.object(rig_v1, "_run", run), self.assertRaises(RenderError):
            rig_v1.RigV1Renderer("godot").render(timeline(), self.pack, self.work)

    def test_timeout(self):
        def run(cmd, timeout_s, env):
            raise subprocess.TimeoutExpired(cmd, timeout_s)
        with mock.patch.object(rig_v1, "_run", run), self.assertRaises(RenderError) as ctx:
            rig_v1.RigV1Renderer("godot").render(timeline(), self.pack, self.work, 5)
        self.assertIn("5s", str(ctx.exception))

    def test_bad_pack_or_timeline_never_spawns_a_process(self):
        run, calls = self.fake_run()
        bad_timelines = [{**timeline(), "total": 61}, {**timeline(), "total": float("nan")}, {**timeline(), "fps": 30},
                         {k: v for k, v in timeline().items() if k != "subs"}, []]
        with mock.patch.object(rig_v1, "_run", run):
            for tl in bad_timelines:
                with self.subTest(tl=str(tl)[:40]), self.assertRaises(RenderError):
                    rig_v1.RigV1Renderer("godot").render(tl, self.pack, self.work)
            (self.pack / "hat.png").unlink()
            with self.assertRaises(RenderError):
                rig_v1.RigV1Renderer("godot").render(timeline(), self.pack, self.work)
        self.assertEqual(calls, [])


class CliTests(unittest.TestCase):
    def test_parser(self):
        args = cli.build_parser().parse_args(["render", "--timeline", "t.json", "--pack", "p", "--out", "o.mp4", "--godot", "g", "--launcher", "xvfb-run -a"])
        self.assertEqual((args.command, args.launcher, args.timeout), ("render", "xvfb-run -a", 900.0))
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["render"])

    def test_placeholder_pack_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli.main(["placeholder-pack", "--out", str(Path(tmp) / "p")]), 0)
            self.assertEqual(packs.validate_pack(Path(tmp) / "p"), [])


class GodotProjectTests(unittest.TestCase):
    def test_project_is_self_contained_and_reads_only_its_arguments(self):
        scene = (rig_v1.PROJECT_DIR / "scene.gd").read_text(encoding="utf-8")
        self.assertIn("--pack=", scene)
        self.assertIn("--timeline=", scene)
        self.assertNotIn("res://sprites", scene)
        self.assertNotIn("HTTPRequest", scene)
        self.assertNotIn("OS.execute", scene)
        self.assertTrue((rig_v1.PROJECT_DIR / "project.godot").is_file())
        self.assertTrue((rig_v1.PROJECT_DIR / "main.tscn").is_file())


if __name__ == "__main__":
    unittest.main()
