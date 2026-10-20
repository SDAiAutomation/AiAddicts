"""Quiz 50 : cartes de chapitre, planification des exports verticaux et garde-fous de rendu."""
import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from engine import quiz_chapter_export, quiz_motion, quiz_shorts
from engine.quiz import CHAPTER_LABELS, chapter_card_block, compile_quiz, validate_motion_blocks
from engine.script import validate_script


_SYLLABLES = ("ba", "ko", "ri", "zu", "me", "tal", "von")
_FIELDS = ("lab", "mining", "teaching", "survey", "archive")
_WORDS = [f"{_SYLLABLES[i % 7]}{_SYLLABLES[(i // 7 + 3) % 7]}{_SYLLABLES[(i * 3) % 7]}x{i}" for i in range(60)]


def questions(count=50, long_text=False):
    result = []
    for i in range(1, count + 1):
        explanation = (f"Explanation {i}: " + "this sentence adds realistic narration length. " * 3) if long_text else f"Because {i}."
        word = _WORDS[i - 1]
        result.append({"question": f"In {_FIELDS[i % 5]} work, what does the term {word} designate?",
                       "choices": [f"{word} answer", f"{word} decoy", f"{word} trap", f"{word} bluff"],
                       "correct_choice": i % 4, "explanation": explanation, "countdown_seconds": 5})
    return result


def script(presentation="motion", mode="five_levels", language="en", long_text=False, **quiz):
    return {"title": "Quiz 50", "niche": "general", "account": "acc", "language": language, "content_format": "quiz",
            "aspect_ratio": "16:9",
            "quiz": {"recipe": "long", "topic": "elements", "difficulty": "progressive", "presentation": presentation,
                     "chapter_mode": mode, "questions": questions(long_text=long_text), **quiz}}


class ChapterCardTests(unittest.TestCase):
    def test_five_cards_open_each_chapter_and_validate(self):
        compiled = compile_quiz(script(long_text=True))
        blocks = compiled["blocks"]
        phases = [b["quiz_phase"] for b in blocks]
        self.assertEqual(len(blocks), 1 + 5 + 100 + 1)
        self.assertEqual(phases.count("chapter"), 5)
        for n, index in enumerate([i for i, p in enumerate(phases) if p == "chapter"], 1):
            self.assertEqual(blocks[index]["quiz_chapter_label"], CHAPTER_LABELS[n - 1])
            self.assertEqual(blocks[index + 1]["quiz_question_number"], (n - 1) * 10 + 1)
            self.assertEqual(blocks[index + 1]["quiz_phase"], "question")
            self.assertEqual((blocks[index]["quiz_first_question"], blocks[index]["quiz_last_question"]), ((n - 1) * 10 + 1, n * 10))
            self.assertEqual(blocks[index].get("hold_after_seconds", 0), 0)
            self.assertEqual(blocks[index]["quiz_presentation"], "motion")
        validate_script(compiled)  # block and character ceilings admit a realistic 50-question script

    def test_card_narration_is_localized_and_short(self):
        self.assertEqual(chapter_card_block(2, "en")["text"], "Level 2 of 5: Medium.")
        self.assertEqual(chapter_card_block(5, "fr")["text"], "Niveau 5 sur 5 : Génie.")
        self.assertEqual(chapter_card_block(1, "xx")["quiz_chapter_title"], "Facile")  # unknown language -> fr default

    def test_recompile_is_idempotent(self):
        once = compile_quiz(script())
        twice = compile_quiz(once)
        self.assertEqual([b["quiz_phase"] for b in once["blocks"]], [b["quiz_phase"] for b in twice["blocks"]])
        self.assertEqual(sum(b["quiz_phase"] == "chapter" for b in twice["blocks"]), 5)

    def test_web_authored_blocks_without_cards_get_them(self):
        base = compile_quiz(script())
        stripped = deepcopy(base)
        stripped["blocks"] = [b for b in stripped["blocks"] if b["quiz_phase"] != "chapter"]
        self.assertEqual(sum(b["quiz_phase"] == "chapter" for b in compile_quiz(stripped)["blocks"]), 5)

    def test_classic_and_legacy_modes_have_no_cards(self):
        classic = compile_quiz(script(presentation="classic"))
        self.assertNotIn("chapter", [b["quiz_phase"] for b in classic["blocks"]])
        self.assertEqual(len(classic["blocks"]), 102)
        legacy = script(mode="legacy")
        legacy["quiz"]["questions"] = legacy["quiz"]["questions"][:25]
        self.assertNotIn("chapter", [b["quiz_phase"] for b in compile_quiz(legacy)["blocks"]])

    def test_missing_or_misplaced_card_is_rejected_for_motion(self):
        compiled = compile_quiz(script())
        broken = deepcopy(compiled)
        broken["blocks"] = [b for b in broken["blocks"] if not (b["quiz_phase"] == "chapter" and b["quiz_chapter_number"] == 3)]
        with self.assertRaisesRegex(ValueError, "hors ordre"):
            validate_motion_blocks(broken)
        validate_motion_blocks(compiled)

    def test_card_belongs_to_its_own_visual_part(self):
        self.assertEqual([quiz_motion.part_index(chapter_card_block(n, "en")) for n in range(1, 6)], [0, 1, 2, 3, 4])

    def test_level_accents_are_legible_on_every_stage_tint(self):
        def lum(colour):
            channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            lin = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return .2126 * lin[0] + .7152 * lin[1] + .0722 * lin[2]
        for theme, accents in (("studio", quiz_motion.LEVEL_ACCENTS_DARK), ("vault", quiz_motion.LEVEL_ACCENTS_DARK),
                               ("minimal", quiz_motion.LEVEL_ACCENTS_LIGHT)):
            for part, accent in enumerate(accents):
                stage = quiz_motion.stage_background(theme, part, 5)
                high, low = sorted((lum(accent), lum(stage)), reverse=True)
                self.assertGreaterEqual((high + .05) / (low + .05), 4.5, (theme, part, accent, stage))

    def test_each_level_has_a_distinct_scene_in_both_orientations(self):
        for width, height in ((1080, 1920), (1920, 1080)):
            signatures = set()
            for n in range(1, 6):
                block = {**chapter_card_block(n, "en"), "quiz_theme": "studio", "quiz_presentation": "motion"}
                events = quiz_motion.scene_events(block, 0, 2.4, width, height, "Poppins")
                self.assertTrue(events)
                joined = "\n".join(events)
                self.assertIn(chapter_card_block(n, "en")["quiz_chapter_title"].upper(), joined)
                signatures.add(joined)
            self.assertEqual(len(signatures), 5)

    def test_card_scene_never_contains_question_or_answer_data(self):
        block = {**chapter_card_block(3, "en"), "quiz_theme": "studio", "quiz_question": "SECRET?", "quiz_choices": ["LEAK"]}
        self.assertNotIn("LEAK", "\n".join(quiz_motion.scene_events(block, 0, 2, 1080, 1920)))


def timeline(card=1.5, question=9.0, reveal=3.0, cards=True, intro=2):
    scenes, t = [], 0.0
    def add(phase, number=None, chapter=None, length=1.0):
        nonlocal t
        scenes.append({"phase": phase, "question_number": number, "chapter_number": chapter, "start": t, "end": t + length})
        t += length
    add("intro", length=intro)
    for n in range(1, 51):
        if cards and n % 10 == 1:
            add("chapter", chapter=(n - 1) // 10 + 1, length=card)
        add("question", n, length=question)
        add("reveal", n, length=reveal)
    add("outro", length=2)
    return scenes


class ChapterSegmentTests(unittest.TestCase):
    def test_card_opens_its_chapter(self):
        segments = quiz_chapter_export.chapter_segments(timeline())
        self.assertEqual([s["label"] for s in segments], list(CHAPTER_LABELS))
        self.assertAlmostEqual(segments[0]["start"], 2.0)
        self.assertAlmostEqual(segments[0]["end"] - segments[0]["start"], 1.5 + 10 * 12)
        self.assertAlmostEqual(segments[1]["start"], segments[0]["end"])
        self.assertTrue(all(s["has_card"] for s in segments))

    def test_cards_are_optional_but_not_partial(self):
        self.assertFalse(quiz_chapter_export.chapter_segments(timeline(cards=False))[0]["has_card"])
        partial = [s for s in timeline() if not (s["phase"] == "chapter" and s["chapter_number"] == 2)]
        with self.assertRaises(ValueError):
            quiz_chapter_export.chapter_segments(partial)

    def test_misordered_phases_are_rejected(self):
        scenes = timeline()
        i = next(i for i, s in enumerate(scenes) if s["phase"] == "reveal")
        scenes[i]["phase"] = "question"
        with self.assertRaises(ValueError):
            quiz_chapter_export.chapter_segments(scenes)

    def test_adapter_reads_measured_timeline(self):
        data = compile_quiz(script())
        report = quiz_motion.build_timeline(data, [4.0 if b["quiz_phase"] != "question" else 9.0 for b in data["blocks"]])
        segments = quiz_chapter_export.chapter_segments(quiz_chapter_export.scenes_from_timeline(report, data["blocks"]))
        self.assertEqual(len(segments), 5)
        self.assertTrue(all(s["has_card"] for s in segments))


class YoutubeTimestampTests(unittest.TestCase):
    def segments(self):
        return quiz_chapter_export.chapter_segments(timeline())

    def test_lines_follow_measured_chapters(self):
        # A 2 s intro cannot be a YouTube chapter (10 s minimum): it merges into the first level, which starts at 0:00.
        text = quiz_chapter_export.youtube_timestamps(self.segments(), ("Easy", "Medium", "Hard", "Expert", "Genius"))
        lines = text.splitlines()
        self.assertEqual(lines[0], "0:00 Level 1: Easy")
        self.assertEqual(lines[1], "2:03 Level 2: Medium")  # 2 s intro + (1.5 s card + 10 x 12 s) = 123.5 s, measured not estimated
        self.assertEqual(len(lines), 5)

    def test_a_long_enough_intro_keeps_its_own_chapter(self):
        segments = quiz_chapter_export.chapter_segments(timeline(intro=12))
        lines = quiz_chapter_export.youtube_timestamps(segments, ("Easy", "Medium", "Hard", "Expert", "Genius")).splitlines()
        self.assertEqual(lines[:2], ["0:00 Intro", "0:12 Level 1: Easy"])
        self.assertEqual(len(lines), 6)

    def test_refuses_chapters_youtube_would_reject(self):
        short = self.segments()
        short[2] = {**short[2], "end": short[2]["start"] + 5}
        with self.assertRaises(ValueError):
            quiz_chapter_export.youtube_timestamps(short, ("a",) * 5)
        with self.assertRaises(ValueError):
            quiz_chapter_export.youtube_timestamps(self.segments()[:4], ("a",) * 5)

    def test_report_carries_chapters_and_timestamps_for_five_level_quizzes_only(self):
        data = compile_quiz(script())
        report = quiz_motion.build_timeline(data, [4.0 if b["quiz_phase"] != "question" else 9.0 for b in data["blocks"]])
        quiz_motion.attach_report(data, report)
        stored = data["generationMetadata"]["quizPresentation"]
        self.assertEqual(len(stored["chapters"]), 5)
        self.assertTrue(stored["youtubeTimestamps"].startswith("0:00 Level 1: Easy\n"))
        self.assertIn("Level 3: Hard", stored["youtubeTimestamps"])
        legacy = script(mode="legacy")
        legacy["quiz"]["questions"] = legacy["quiz"]["questions"][:25]
        compiled = compile_quiz(legacy)
        quiz_motion.attach_report(compiled, quiz_motion.build_timeline(compiled, [4.0 if b["quiz_phase"] != "question" else 9.0 for b in compiled["blocks"]]))
        self.assertNotIn("chapters", compiled["generationMetadata"]["quizPresentation"])


class ShortPlanTests(unittest.TestCase):
    def data(self):
        return compile_quiz(script())

    def durations(self, data, question=9.0, reveal=4.0, card=1.5, other=2.0):
        return [{"question": question, "reveal": reveal, "chapter": card}.get(b["quiz_phase"], other) for b in data["blocks"]]

    def test_chapter_under_the_limit_is_one_short(self):
        data = self.data()
        plans = quiz_shorts.plan_exports(data, self.durations(data))
        self.assertEqual([p["file"] for p in plans], ["quiz_easy.mp4", "quiz_medium.mp4", "quiz_hard.mp4", "quiz_expert.mp4", "quiz_genius.mp4"])
        self.assertTrue(all(p["short_eligible"] and p["parts"] == 1 for p in plans))
        self.assertEqual(plans[2]["first_question"], 21)
        self.assertEqual(plans[2]["last_question"], 30)
        self.assertEqual(len(plans[0]["blocks"]), 21)
        self.assertAlmostEqual(plans[0]["expected_duration"], 1.5 + 10 * 13)

    def test_chapter_over_the_limit_is_split_never_sped_up_or_cut(self):
        data = self.data()
        plans = quiz_shorts.plan_exports(data, self.durations(data, question=14.0, reveal=6.0))  # 201.5 s / chapter
        easy = [p for p in plans if p["chapter"] == 1]
        self.assertEqual([p["file"] for p in easy], ["quiz_easy_part1.mp4", "quiz_easy_part2.mp4"])
        covered = [q for p in easy for q in range(p["first_question"], p["last_question"] + 1)]
        self.assertEqual(covered, list(range(1, 11)))  # every question exactly once, in order
        for part in easy:
            self.assertLessEqual(part["expected_duration"], quiz_shorts.SHORT_MAX_SECONDS - quiz_shorts.SHORT_MARGIN_SECONDS)
            self.assertEqual(data["blocks"][part["blocks"][0]]["quiz_phase"], "chapter")  # each part opens with the card
            phases = [data["blocks"][i]["quiz_phase"] for i in part["blocks"][1:]]
            self.assertEqual(phases, ["question", "reveal"] * (len(phases) // 2))
        self.assertAlmostEqual(sum(p["expected_duration"] - 1.5 for p in easy), 200.0)

    def test_partition_is_minimal_and_balanced(self):
        self.assertEqual(quiz_shorts.partition([10.0] * 10, 2.0, 120.0), [(0, 10)])
        spans = quiz_shorts.partition([20.0] * 10, 2.0, 120.0)
        self.assertEqual(len(spans), 2)
        self.assertEqual({b - a for a, b in spans}, {5})
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.partition([200.0], 2.0, 120.0)

    def test_unexportable_scripts_are_refused(self):
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.require_exportable(compile_quiz(script(presentation="classic")))
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.require_exportable(compile_quiz({**script(mode="legacy"), "quiz": {**script(mode="legacy")["quiz"], "questions": questions()[:25]}}))
        data = self.data()
        data["blocks"] = data["blocks"][:-5]
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.require_exportable(data)

    def test_missing_measurements_are_refused(self):
        data = self.data()
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.plan_exports(data, [1.0] * 3)


class ExportIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = compile_quiz(script())
        (self.tmp / "audio").mkdir()
        for index, block in enumerate(self.data["blocks"], 1):
            quiz_shorts.audio_path(self.tmp, index, block).write_bytes(b"x")

    def run_export(self, fail_chapter=None, **kwargs):
        def fake_render(data, work, plan, out):
            if plan["chapter"] == fail_chapter:
                raise quiz_shorts.ExportError(f"boom {work}/secret")
            (out / plan["file"]).write_bytes(b"mp4")
            return {**{k: plan[k] for k in ("chapter", "label", "part", "parts", "file", "first_question", "last_question")}, "status": "ready", "error": None}
        with mock.patch.object(quiz_shorts.tts, "get_playback_duration_seconds", return_value=5.0), \
                mock.patch.object(quiz_shorts, "render_plan", side_effect=fake_render):
            return quiz_shorts.export_chapters(self.data, self.tmp, **kwargs)

    def test_one_failed_chapter_does_not_stop_or_corrupt_the_others(self):
        manifest = self.run_export(fail_chapter=3)
        status = {i["chapter"]: i["status"] for i in manifest["items"]}
        self.assertEqual(status, {1: "ready", 2: "ready", 3: "failed", 4: "ready", 5: "ready"})
        failed = next(i for i in manifest["items"] if i["chapter"] == 3)
        self.assertNotIn(str(self.tmp), failed["error"])  # no internal path leaks to the user
        self.assertEqual(json.loads((self.tmp / "shorts" / "manifest.json").read_text())["items"][2]["status"], "failed")
        self.assertFalse((self.tmp / "shorts" / "quiz_hard.mp4").exists())

    def test_only_requested_chapters_render_and_invalid_ones_are_rejected(self):
        self.assertEqual([i["chapter"] for i in self.run_export(chapters=[2, 4])["items"]], [2, 4])
        for bad in ([0], [6], [True], ["1"]):
            with self.assertRaises(quiz_shorts.ExportError):
                self.run_export(chapters=bad)

    def test_missing_master_audio_is_a_clear_error(self):
        quiz_shorts.audio_path(self.tmp, 7, self.data["blocks"][6]).unlink()
        with self.assertRaisesRegex(quiz_shorts.ExportError, "régénère"):
            self.run_export()

    def test_render_refuses_output_outside_the_workspace_and_odd_names(self):
        plan = {"file": "quiz_easy.mp4", "chapter": 1, "blocks": [0]}
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.render_plan(self.data, self.tmp, plan, self.tmp.parent)
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.render_plan(self.data, self.tmp, {**plan, "file": "../evil.mp4"}, self.tmp / "shorts")

    def test_validate_output_checks_size_audio_and_duration(self):
        out = self.tmp / "a.mp4"
        out.write_bytes(b"x")
        good = {"width": 1080, "height": 1920, "has_audio": True, "duration": 100.0}
        with mock.patch.object(quiz_shorts, "probe", return_value=good):
            self.assertEqual(quiz_shorts.validate_output(out, 100.1)["height"], 1920)
            with self.assertRaisesRegex(quiz_shorts.ExportError, "désynchronisés"):
                quiz_shorts.validate_output(out, 101.0)
        for patch, message in (({"width": 1920, "height": 1080}, "Résolution"), ({"has_audio": False}, "audio")):
            with mock.patch.object(quiz_shorts, "probe", return_value={**good, **patch}):
                with self.assertRaisesRegex(quiz_shorts.ExportError, message):
                    quiz_shorts.validate_output(out, 100.0)
        out.write_bytes(b"")
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_shorts.validate_output(out, 100.0)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg requis")
class PlaybackDurationTests(unittest.TestCase):
    def test_decoded_duration_excludes_encoder_delay(self):
        import subprocess
        from engine import tts
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.mp3"
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=2", "-c:a", "libmp3lame", str(path)],
                           check=True, capture_output=True)
            decoded, header = tts.get_playback_duration_seconds(str(path)), tts.get_duration_seconds(str(path))
            self.assertAlmostEqual(decoded, 2.0, delta=0.03)
            self.assertLessEqual(decoded, header + 1e-6)


if __name__ == "__main__":
    unittest.main()
