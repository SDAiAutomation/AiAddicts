"""Gate 3: what is shown while the narrator talks (visual beats, word cards), Pip's head-clutching pose, and the size allowance."""
import copy
import json
import re
import unittest
from pathlib import Path

from growthos.engine.story_animation import pipeline, quality, shotplan, timeline as timeline_lib
from growthos.engine.story_animation.test_timeline_lib import alignment

FX = Path(__file__).parent / "fixtures"
SCENE = (Path(__file__).parent / "godot" / "rig_v1" / "scene.gd").read_text(encoding="utf-8")


def entry(start, end, speaker="narrator", **over):
    actors = [
        {"role": "ros", "side": "left", "facing": "right", "mood": "neutral", "gesture": "idle", "props": []},
        {"role": "pip", "side": "right", "facing": "left", "mood": "neutral", "gesture": "idle", "props": []},
    ]
    base = {"index": 0, "start": start, "end": end, "setting": "street", "background": "bg_street", "shot_type": "wide",
            "camera": {"move": "push_in", "zoom_from": 1.0, "zoom_to": 1.08}, "speaker": speaker, "actors": actors, "transition_in": "fade"}
    base.update(over)
    return base


class NarratedBeats(unittest.TestCase):
    def test_a_long_narrated_shot_is_cut_into_contiguous_beats_of_at_least_four_seconds(self):
        beats = shotplan.narrated_beats(entry(10.0, 25.0), 3)
        self.assertEqual(len(beats), 3)
        self.assertEqual(beats[0]["start"], 10.0)
        self.assertEqual(beats[-1]["end"], 25.0)
        for before, after in zip(beats, beats[1:]):
            self.assertEqual(before["end"], after["start"])
        for beat in beats:
            self.assertGreaterEqual(beat["end"] - beat["start"], shotplan.BEAT_SECONDS - 0.01)
            self.assertEqual((beat["speaker"], beat["setting"], beat["background"]), ("narrator", "street", "bg_street"))
        self.assertEqual([b["index"] for b in beats], [3, 4, 5])
        self.assertEqual([b["transition_in"] for b in beats], ["fade", "cut", "cut"])

    def test_the_number_of_beats_is_bounded(self):
        self.assertEqual(len(shotplan.narrated_beats(entry(0.0, 60.0), 0)), shotplan.MAX_BEATS)

    def test_short_narrated_shots_character_shots_and_empty_shots_are_left_alone(self):
        for e in (entry(0.0, 7.9), entry(0.0, 20.0, speaker="pip"), entry(0.0, 20.0, actors=[])):
            out = shotplan.narrated_beats(e, 7)
            self.assertEqual(len(out), 1)
            self.assertEqual({k: v for k, v in out[0].items() if k != "index"}, {k: v for k, v in e.items() if k != "index"})

    def test_the_beats_vary_the_picture(self):
        beats = shotplan.narrated_beats(entry(0.0, 24.0), 0)
        kinds = {(b["shot_type"], b["camera"]["move"], b["focus"], b["empty"]) for b in beats}
        self.assertEqual(len(kinds), len(beats))                      # no two beats look the same
        self.assertTrue(any(b["focus"] for b in beats))               # a reaction on a listener
        self.assertTrue(any(b["empty"] for b in beats))               # the setting alone
        self.assertEqual(beats[0]["camera"]["move"], "push_in")       # the first beat establishes

    def test_only_actors_at_rest_get_a_listening_pose_and_authored_acting_is_never_changed(self):
        e = entry(0.0, 24.0)
        e["actors"][1].update(gesture="accuse", mood="angry")
        beats = shotplan.narrated_beats(e, 0)
        for b in beats:
            pip = next(a for a in b["actors"] if a["role"] == "pip")
            if b["focus"] != "pip":
                self.assertEqual((pip["gesture"], pip["mood"]), ("accuse", "angry"))
        ros_gestures = {next(a for a in b["actors"] if a["role"] == "ros")["gesture"] for b in beats}
        self.assertGreater(len(ros_gestures), 1)                      # the listener who was at rest now moves
        self.assertNotIn("clutch_head", ros_gestures)
        self.assertEqual(e["actors"][1]["gesture"], "accuse")         # the input is not mutated

    def test_a_reaction_beat_frames_a_listener_in_close_up_with_a_mood(self):
        for b in shotplan.narrated_beats(entry(0.0, 24.0), 0):
            if b["focus"]:
                self.assertEqual(b["shot_type"], "close_up")
                framed = next(a for a in b["actors"] if a["role"] == b["focus"])
                self.assertIn(framed["mood"], shotplan.REACTION_MOODS)


class WordCards(unittest.TestCase):
    TEXT = "Dans l'annexe de « 1984 », il décrit le « néoparler » : une langue."

    def test_a_term_between_quotation_marks_is_shown_while_it_is_spoken(self):
        al = alignment(self.TEXT, 0.1)
        cards = timeline_lib.cards_for(self.TEXT, al, 5.0, 5.0 + 0.1 * len(self.TEXT))
        self.assertEqual([c["text"] for c in cards], ["1984", "néoparler"])
        self.assertAlmostEqual(cards[1]["start"], 5.0 + 0.1 * self.TEXT.index("néoparler"), places=3)
        self.assertAlmostEqual(cards[1]["end"] - cards[1]["start"], timeline_lib.CARD_SECONDS, places=3)

    def test_nothing_is_shown_when_the_alignment_does_not_match_or_the_term_is_long(self):
        self.assertEqual(timeline_lib.cards_for(self.TEXT, alignment("autre texte", 0.1), 0.0, 3.0), [])
        long_text = "Il dit « une phrase beaucoup trop longue pour une carte »."
        self.assertEqual(timeline_lib.cards_for(long_text, alignment(long_text, 0.1), 0.0, 6.0), [])
        self.assertEqual(timeline_lib.cards_for("Rien entre guillemets ici.", alignment("Rien entre guillemets ici.", 0.1), 0.0, 3.0), [])

    def test_the_timeline_carries_the_cards_without_overlap(self):
        texts = [self.TEXT, "Le mot « injuste » a disparu, puis « liberté »."]
        lines = [{"who": "narrator", "text": t, "duration_s": 0.1 * len(t), "alignment": alignment(t, 0.1), "envelope": [1.0] * int(0.1 * len(t) * 24)} for t in texts]
        tl = timeline_lib.build_timeline(lines, max_total=200.0)
        self.assertEqual([c["text"] for c in tl["cards"]], ["1984", "néoparler", "injuste", "liberté"])
        for a, b in zip(tl["cards"], tl["cards"][1:]):
            self.assertLessEqual(a["end"], b["start"])


class PilotScenarios(unittest.TestCase):
    def test_the_narrated_shots_of_a_pilot_scenario_are_no_longer_one_static_composition(self):
        story = json.loads((FX / "story_v21_ville_sans_mots.json").read_text(encoding="utf-8"))["story"]
        lines = []
        for shot in story["shots"]:
            dur = len(shot["dialogue"]) / 16.5
            lines.append({"who": "narrator" if shot["speaker_id"] == "narrator" else ("pip" if shot["speaker_id"] == "pip" else "ros"),
                          "text": shot["dialogue"], "duration_s": dur, "alignment": alignment(shot["dialogue"], dur / len(shot["dialogue"])),
                          "envelope": [1.0] * int(dur * 24)})
        tl = timeline_lib.build_timeline(lines, max_total=200.0)
        plan = shotplan.build_shot_plan(story, tl, pipeline.rig_roles(story))
        narrated = [s for s in plan if s["speaker"] == "narrator"]
        longest_static = max(s["end"] - s["start"] for s in narrated)
        self.assertLessEqual(longest_static, 8.0)       # before: 15 s on one composition
        self.assertTrue(any(s["empty"] for s in narrated if "empty" in s))
        self.assertTrue(tl["cards"])                    # « injuste », « 1984 », « néoparler »... appear on screen


class PoseAndSize(unittest.TestCase):
    def test_pips_hands_hold_the_top_of_his_head_never_his_eyes(self):
        block = SCENE[SCENE.index('"clutch_head":'):SCENE.index('"hands_on_hips":')]
        match = re.search(r'role == "pip":.*?hold_l = Vector2\((-?\d+\.\d+), (-?\d+\.\d+)\).*?hold_r = Vector2\((-?\d+\.\d+), (-?\d+\.\d+)\)', block, re.S)
        self.assertIsNotNone(match, "Pip needs his own hand targets")
        lx, ly, rx, ry = (float(v) for v in match.groups())
        self.assertLess(max(ly, ry), -330.0)            # his glasses are about 250 px above the neck anchor
        self.assertGreaterEqual(min(abs(lx), abs(rx)), 200.0)

    REPORT = {"audio_duration_s": 1.0, "width": 1080, "height": 1920, "fps": 24, "black": [], "freeze": [], "mean_volume_db": -20.0, "max_volume_db": -3.0}

    def problems(self, seconds, mib):
        report = dict(self.REPORT, video_duration_s=seconds, audio_duration_s=seconds, size_bytes=int(mib * 1048576))
        return [p.kind for p in quality.judge_media(report, {"width": 1080, "height": 1920, "fps": 24})]

    def test_longer_videos_get_a_larger_size_allowance(self):
        self.assertEqual(self.problems(100, 36.2), [])            # the first real render
        self.assertEqual(self.problems(180, 55.0), [])            # allowed: 0.4 MiB per second
        self.assertEqual(self.problems(60, 41.0), ["size"])       # short videos keep the 40 MiB ceiling
        self.assertEqual(self.problems(180, 80.0), ["size"])


if __name__ == "__main__":
    unittest.main()
