"""Sous-titres Faceloop du récit illustré : cues décalés par scène, style `off`, échappement/validation du chemin, bout en bout hors ligne.
Doublures uniquement (voix simulée, images de substitution) : aucun appel payant."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from growthos.engine import captions
from growthos.engine.story_visual import cost, pipeline, render, sample, subtitles, timing, voice
from growthos.engine.story_visual.test_pipeline import RATES, VOICE, Harness, moral_with_voice


def _timeline_and_voices():
    plan = sample.moral_plan()
    audio = {s["id"]: 2.0 for s in plan["scenes"]}
    timeline = timing.schedule(plan, audio)
    voices = {s["id"]: {"words": [{"text": f"{s['id']}a", "start": 0.0, "end": 0.5}, {"text": f"{s['id']}b", "start": 0.5, "end": 1.0}]}
              for s in plan["scenes"]}
    return timeline, voices


class TestCues(unittest.TestCase):
    def test_words_are_shifted_by_each_scenes_audio_start(self):
        timeline, voices = _timeline_and_voices()
        cues = subtitles.build_cues(timeline, voices)
        self.assertEqual(len(cues), len(timeline["scenes"]))  # 2 mots par scène : un cue par scène
        for cue, slot in zip(cues, timeline["scenes"]):
            self.assertAlmostEqual(cue["start"], slot["audio_start"], places=3)
            self.assertAlmostEqual(cue["words"][1]["start"], slot["audio_start"] + 0.5, places=3)
            self.assertLessEqual(cue["end"], slot["end"] + 0.2)
        self.assertEqual(subtitles.issues(cues, None, captions.CAPTIONS_OFF, timeline["total_s"]), [])

    def test_malformed_words_are_ignored_and_a_silent_scene_has_no_cue(self):
        timeline, voices = _timeline_and_voices()
        voices["s1"]["words"] = [{"text": "", "start": 0, "end": 1}, {"start": 0, "end": 1}, "x", {"text": "ok", "start": "a", "end": 1}]
        cues = subtitles.build_cues(timeline, voices)
        self.assertEqual(len(cues), len(timeline["scenes"]) - 1)

    def test_issues_flag_no_cue_missing_ass_and_cues_past_the_end(self):
        timeline, voices = _timeline_and_voices()
        cues = subtitles.build_cues(timeline, voices)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        ass = subtitles.write(cues, tmp, "x", "bold_stroke")
        self.assertEqual(subtitles.issues(cues, ass, "bold_stroke", timeline["total_s"]), [])
        empty = subtitles.write([], tmp, "y", "bold_stroke")
        self.assertEqual(len(subtitles.issues([], empty, "bold_stroke", 10)), 2)  # .ass sans événement + aucun cue
        self.assertTrue(subtitles.issues(cues, tmp / "absent.ass", "bold_stroke", timeline["total_s"]))
        self.assertTrue(any("outside" in i for i in subtitles.issues(cues, ass, "bold_stroke", 1.0)))

    def _cues_with(self, mutate):
        timeline, voices = _timeline_and_voices()
        mutate(voices, timeline)
        return timeline, subtitles.build_cues(timeline, voices)

    def test_issues_stay_silent_on_well_timed_words(self):
        timeline, cues = self._cues_with(lambda v, t: None)
        self.assertEqual(subtitles.issues(cues, None, "off", timeline["total_s"], timeline), [])

    def test_issues_flag_a_word_that_ends_before_it_starts(self):
        def bad(voices, _):
            voices["s1"]["words"][1] = {"text": "x", "start": 0.9, "end": 0.4}
        timeline, cues = self._cues_with(bad)
        out = subtitles.issues(cues, None, "off", timeline["total_s"], timeline)
        self.assertTrue(any("ends before it starts" in i for i in out), out)

    def test_issues_flag_a_word_overflowing_its_scene_block(self):
        def bad(voices, timeline):
            block = timeline["scenes"][1]["audio_start"] - timeline["scenes"][0]["audio_start"]
            voices["s1"]["words"][1] = {"text": "x", "start": 0.5, "end": block + 1.0}
        timeline, cues = self._cues_with(bad)
        out = subtitles.issues(cues, None, "off", timeline["total_s"] + 5, timeline)
        self.assertTrue(any("overflow" in i for i in out), out)

    def test_a_word_starting_on_a_block_boundary_up_to_rounding_is_not_an_overflow(self):
        timeline = {"scenes": [{"audio_start": 0.15}, {"audio_start": 14.85}], "total_s": 30.0}
        # 14.849999999999998 < 14.85 : le mot appartient au 2e bloc, pas au 1er
        cues = [{"index": 1, "start": 14.85, "end": 15.25, "text": "His",
                 "words": [{"text": "His", "start": 14.849999999999998, "end": 15.249999999999998}]}]
        self.assertEqual(subtitles.issues(cues, None, "off", 30.0, timeline), [])

    def test_issues_flag_overlapping_cues(self):
        timeline, cues = self._cues_with(lambda v, t: None)
        cues[1] = {**cues[1], "start": cues[0]["end"] - 0.5}
        out = subtitles.issues(cues, None, "off", timeline["total_s"], timeline)
        self.assertTrue(any("overlap" in i for i in out), out)

    def test_off_writes_the_srt_but_no_ass(self):
        timeline, voices = _timeline_and_voices()
        cues = subtitles.build_cues(timeline, voices)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertIsNone(subtitles.write(cues, tmp, "story", "off"))
        self.assertTrue((tmp / "story.srt").is_file())
        self.assertFalse((tmp / "captions.ass").exists())
        self.assertEqual(subtitles.issues([], None, "off", 10), [])  # off : aucun .ass ni cue exigés


class TestAssFilter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_filter_uses_the_bare_name_and_the_folder_as_cwd(self):
        # Dossier avec espace, apostrophe, virgule, crochet : rien de tout cela n'entre dans le graphe de filtres.
        folder = self.tmp / "O'Brien, [x]; a b"
        folder.mkdir()
        (folder / "captions.ass").write_text("x", encoding="utf-8")
        flt, cwd = render._ass_filter(folder / "captions.ass")
        self.assertEqual(flt, "ass=filename=captions.ass")
        self.assertEqual(Path(cwd), folder.resolve())

    def test_fonts_are_copied_next_to_the_ass_and_referenced_relatively(self):
        src = self.tmp / "src"
        src.mkdir()
        (src / "Poppins-Bold.ttf").write_bytes(b"f")
        (src / "other.txt").write_bytes(b"x")
        folder = self.tmp / "o"
        folder.mkdir()
        (folder / "captions.ass").write_text("x", encoding="utf-8")
        flt, cwd = render._ass_filter(folder / "captions.ass", src)
        self.assertEqual(flt, "ass=filename=captions.ass:fontsdir=fonts")
        self.assertTrue((Path(cwd) / "fonts" / "Poppins-Bold.ttf").is_file())
        self.assertFalse((Path(cwd) / "fonts" / "other.txt").exists())
        with self.assertRaises(render.RenderError):
            render._ass_filter(folder / "captions.ass", self.tmp / "absent-dir")

    def test_the_graph_carries_fontsdir(self):
        src = self.tmp / "src"
        src.mkdir()
        (src / "Poppins-Bold.ttf").write_bytes(b"f")
        timeline, _ = _timeline_and_voices()
        files = []
        for s in timeline["scenes"]:
            f = self.tmp / f"{s['id']}.bin"
            f.write_bytes(b"x")
            files.append(f)
        ass = self.tmp / "captions.ass"
        ass.write_text("x", encoding="utf-8")
        seen = {}
        with patch.object(render, "_scene_clip"), patch.object(render, "probe", return_value={}),                 patch.object(render, "_run", side_effect=lambda cmd, cwd=None: seen.update(cmd=cmd, cwd=cwd)):
            render.render_story(files, timeline, files, self.tmp / "o.mp4", self.tmp / "w", captions_ass=ass, fonts_dir=src)
        self.assertIn("ass=filename=captions.ass:fontsdir=fonts[vsub]", seen["cmd"][seen["cmd"].index("-filter_complex") + 1])

    def test_unsafe_names_and_missing_files_are_refused(self):
        for name in ("a:b.ass", "a'b.ass", "a,b.ass", "a[b].ass", "a b.ass", "a.srt", "a.ass.txt"):
            path = self.tmp / name
            try:
                path.write_text("x", encoding="utf-8")
            except OSError:
                continue  # nom interdit par le système de fichiers (Windows) : déjà inatteignable
            with self.assertRaises(render.RenderError, msg=name):
                render._ass_filter(path)
        with self.assertRaises(render.RenderError):
            render._ass_filter(self.tmp / "absent.ass")

    def test_the_ass_is_inserted_after_the_fades_and_ffmpeg_runs_in_its_folder(self):
        timeline, _ = _timeline_and_voices()
        ids = [s["id"] for s in timeline["scenes"]]
        files = []
        for i in ids:
            f = self.tmp / f"{i}.bin"
            f.write_bytes(b"x")
            files.append(f)
        ass = self.tmp / "captions.ass"
        ass.write_text("x", encoding="utf-8")
        seen = {}
        with patch.object(render, "_scene_clip"), patch.object(render, "probe", return_value={}), \
                patch.object(render, "_run", side_effect=lambda cmd, cwd=None: seen.update(cmd=cmd, cwd=cwd)):
            render.render_story(files, timeline, files, self.tmp / "o.mp4", self.tmp / "w", captions_ass=ass)
            graph = seen["cmd"][seen["cmd"].index("-filter_complex") + 1]
            self.assertIn("ass=filename=captions.ass[vsub]", graph)
            self.assertEqual(seen["cmd"][seen["cmd"].index("-map") + 1], "[vsub]")
            self.assertEqual(Path(seen["cwd"]), self.tmp.resolve())
            render.render_story(files, timeline, files, self.tmp / "o.mp4", self.tmp / "w")  # off : rien d'incrusté
            self.assertNotIn("ass=", seen["cmd"][seen["cmd"].index("-filter_complex") + 1])
            self.assertIsNone(seen["cwd"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class TestPipelineCaptions(Harness):
    def run_with(self, script_extra, tenant):
        ports = self.ports()
        return pipeline.run({"content_format": "story_visual", "story_plan": moral_with_voice(), **script_extra}, ports,
                            self.tmp / "w", tenant_id=tenant), ports

    def test_default_style_burns_faceloop_captions_and_leaves_the_plan_untouched(self):
        result, _ = self.run_with({}, "t-default")
        folder = Path(result["video"]).parent
        ass = (folder / "captions.ass").read_text(encoding="utf-8")
        self.assertIn("Dialogue:", ass)
        self.assertTrue((folder / f"{moral_with_voice()['story_id']}.srt").is_file())
        self.assertEqual(result["caption_style"], captions.DEFAULT_CAPTION_STYLE)
        self.assertEqual(result["review"], [])
        self.assertFalse(list(folder.glob("text-*.png")))  # plus de calque on_screen_text

    def test_off_style_burns_nothing(self):
        result, _ = self.run_with({"caption_style": "off"}, "t-off")
        folder = Path(result["video"]).parent
        self.assertFalse((folder / "captions.ass").exists())
        self.assertEqual(result["review"], [])

    def test_unknown_style_falls_back_to_the_default(self):
        result, _ = self.run_with({"caption_style": "nope"}, "t-unknown")
        self.assertEqual(result["caption_style"], captions.DEFAULT_CAPTION_STYLE)

    def test_changing_the_style_is_not_an_idempotent_replay(self):
        first, _ = self.run_with({"caption_style": "sleek"}, "t-replay")
        again, ports = self.run_with({"caption_style": "sleek"}, "t-replay")
        self.assertTrue(again.get("idempotent_replay"))
        other, ports = self.run_with({"caption_style": "off"}, "t-replay")
        self.assertFalse(other.get("idempotent_replay"))

    def _counting(self, tenant, script_extra, mutate_done=None):
        calls = {"credit": 0, "quota": 0}
        def ports():
            return self.ports(reserve_credit=lambda: calls.__setitem__("credit", calls["credit"] + 1) or True,
                              consume_quota=lambda: calls.__setitem__("quota", calls["quota"] + 1) or True)
        script = {"content_format": "story_visual", "story_plan": moral_with_voice(), **script_extra}
        first = pipeline.run(script, ports(), self.tmp / "w", tenant_id=tenant)
        self.assertEqual(calls, {"credit": 1, "quota": 1})
        done = Path(first["video"]).parent / "done.json"
        if mutate_done:
            data = json.loads(done.read_text(encoding="utf-8"))
            mutate_done(data)
            done.write_text(json.dumps(data), encoding="utf-8")
        return script, ports, calls

    def test_identical_replay_reserves_no_credit_and_no_quota(self):
        script, ports, calls = self._counting("t-free-replay", {"caption_style": "sleek"})
        again = pipeline.run(script, ports(), self.tmp / "w", tenant_id="t-free-replay")
        self.assertTrue(again["idempotent_replay"])
        self.assertEqual(calls, {"credit": 1, "quota": 1})

    def test_a_legacy_done_json_without_caption_style_replays_for_free_with_the_default_style(self):
        script, ports, calls = self._counting("t-legacy", {}, lambda d: d.pop("caption_style"))
        again = pipeline.run(script, ports(), self.tmp / "w", tenant_id="t-legacy")
        self.assertTrue(again["idempotent_replay"])
        self.assertEqual(calls, {"credit": 1, "quota": 1})

    def test_a_legacy_done_json_does_not_replay_for_another_style(self):
        script, ports, calls = self._counting("t-legacy2", {}, lambda d: d.pop("caption_style"))
        again = pipeline.run({**script, "caption_style": "off"}, ports(), self.tmp / "w", tenant_id="t-legacy2")
        self.assertFalse(again.get("idempotent_replay"))
        self.assertEqual(calls, {"credit": 2, "quota": 2})

    def test_changing_the_style_costs_a_new_credit_and_quota(self):
        script, ports, calls = self._counting("t-cost", {"caption_style": "sleek"})
        other = pipeline.run({**script, "caption_style": "off"}, ports(), self.tmp / "w", tenant_id="t-cost")
        self.assertFalse(other.get("idempotent_replay"))
        self.assertEqual(calls, {"credit": 2, "quota": 2})

    def test_a_voice_without_timed_words_is_delivered_for_review(self):
        class Mute(voice.SimulatedVoiceProvider):
            def __call__(self, text, voice_id, out_path):
                result = super().__call__(text, voice_id, out_path)
                result.words = []
                return result
        ports = self.ports(voice_provider=Mute("en"))
        result = pipeline.run({"content_format": "story_visual", "story_plan": moral_with_voice()}, ports, self.tmp / "w", tenant_id="t-mute")
        self.assertTrue(result["needs_review"])
        self.assertTrue(any(i.startswith("captions: no cue") for i in result["review"]))


if __name__ == "__main__":
    unittest.main()
