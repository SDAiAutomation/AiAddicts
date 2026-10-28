"""Offline end-to-end render of the storyboard path: fake voices (sine WAVs) and placeholder pictures, real ffmpeg assembly,
real mix, real ffprobe measurement. No provider is called. Skipped when ffmpeg is not installed."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from growthos.engine import video
from growthos.engine.story_animation import measure, pipeline, quality, storyboard, voices
from growthos.engine.story_animation.test_timeline_lib import alignment

FIXTURE = Path(__file__).parent / "fixtures" / "rig_v1_story.json"
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _sine_wav(path: Path, seconds: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds:.3f}",
                    "-af", "volume=0.5", "-ac", "1", "-ar", "44100", str(path)], check=True, capture_output=True)


def _placeholder(path: Path, seed: int) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=1024x1536:rate=1:duration=1",
                    "-vf", f"hue=h={seed * 37 % 360}", "-frames:v", "1", str(path)], check=True, capture_output=True)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe not installed")
class OfflineStoryboardRender(unittest.TestCase):
    def test_fixture_renders_a_real_mp4(self):
        s = json.loads(FIXTURE.read_text(encoding="utf-8"))
        s["caption_style"] = "neon"
        s["story"]["shots"] = s["story"]["shots"][:4]      # keep the test short
        s["story"]["shots"][2]["transition_in"] = "fade"
        s["story"]["shots"][0]["dialogue"] += (" Un matin, la file s'allongeait devant la porte, et personne ne savait pourquoi."
                                               " Quelqu'un a sorti son téléphone. Puis tout le monde reculait, sans un mot.")
        image_calls = []

        def synthesize(text, voice_id, wav):
            seconds = round(len(text) / 15.0, 2)
            _sine_wav(Path(wav), seconds)
            return {"duration_s": seconds, "alignment": alignment(text, seconds / len(text)), "envelope": [1.0] * 10}

        def generate_image(prompt, out):
            image_calls.append(prompt)
            if len(image_calls) == 2:
                return None                  # one persistent failure: that beat must reuse a neighbour
            _placeholder(Path(out), len(image_calls))
            return out

        def call_llm(messages, model):
            rows = json.loads(messages[1]["content"])["beats"]
            return json.dumps({"beats": [{"i": r["i"], "show": f"Placeholder picture number {r['i']} of the story.",
                                          "shot": "wide", "camera": "shake" if r["i"] == 1 else "push_in"}
                                         for r in rows]}), {"input": 100, "output": 100}

        events, published = {}, {}
        sb = storyboard.StoryboardPorts(generate_image=generate_image, call_llm=call_llm, llm_model="fake",
                                        usd_per_image=0.05, image_attempts=1, fps=12)

        def check(final):
            report = measure.measure(final)
            published["report"] = report
            return quality.judge_media(report, {"width": 1080, "height": 1920, "fps": 12})

        with tempfile.TemporaryDirectory() as tmp:
            ports = pipeline.Ports(
                authorize=lambda: None, moderate=lambda script: None, ready=lambda: [],
                estimate=lambda seconds, chars: storyboard.estimate(seconds, chars, sb),
                reserve_credit=lambda: True, refund_credit=lambda: None,
                record_event=lambda name, **props: events.__setitem__(name, props),
                synthesize=synthesize, render=lambda tl, wd: None,
                mix=lambda rendered, starts, tl, out: voices.mix_and_mux(rendered.video_path, starts, tl["total"], out),
                check_quality=check,
                publish=lambda final, tl, review: published.update(final=Path(final), review=review, total=tl["total"]) or {"video_url": "local"},
                catalog=pipeline.RIG_V1_CATALOG, renderer="storyboard", storyboard=sb,
            )
            with mock.patch.object(video, "_KENBURNS_SUPERSAMPLE", 1):   # speed only; production keeps the supersampling
                out = pipeline.run(s, ports, Path(tmp) / "job")
            final = published["final"]
            self.assertTrue(final.is_file())
            report = published["report"]
            black = quality.parse_blackdetect(subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", str(final), "-vf", "blackdetect=d=0.5:pix_th=0.1", "-an", "-f", "null", "-"],
                capture_output=True, text=True).stderr)
            work = Path(tmp) / "job" / "storyboard"
            self.assertTrue((work / "captions_src.ass").is_file())
            n_clips = len(list((work / "clips").glob("beat_*.mp4")))

        self.assertEqual((report["width"], report["height"]), (1080, 1920))
        self.assertAlmostEqual(report["fps"], 12.0, places=2)
        self.assertAlmostEqual(report["video_duration_s"], published["total"], delta=0.1)
        self.assertAlmostEqual(report["audio_duration_s"], report["video_duration_s"], delta=0.1)
        self.assertEqual(black, [])
        self.assertEqual(out["video_url"], "local")
        done = events["generation_completed"]
        self.assertEqual(done["renderer"], "storyboard")
        self.assertEqual(done["beat_count"], n_clips)
        self.assertEqual(done["images_reused"], 1)
        self.assertEqual(done["image_count"], n_clips - 1)
        self.assertEqual(done["caption_style"], "neon")
        self.assertEqual(done["direction_source"], "llm")
        self.assertGreater(n_clips, len(s["story"]["shots"]))   # more beats than narrated shots
        self.assertEqual([p for p in published["review"] if p.severity == quality.BLOCKING], [])


if __name__ == "__main__":
    unittest.main()
