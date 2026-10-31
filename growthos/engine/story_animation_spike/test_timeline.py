"""Offline tests; no providers, secrets, network, DB or production worker."""
import unittest

from growthos.engine.story_animation_spike.timeline import build_timeline, frame_state


def sample():
    return {
        "characters": [{"id": "neo"}, {"id": "orion"}],
        "shots": [
            {"id": "s1", "speaker_id": "neo", "duration_s": 2.5, "action": "talk"},
            {"id": "s2", "speaker_id": "orion", "duration_s": 3, "action": "gesture", "emotion": "happy"},
            {"id": "s3", "speaker_id": "neo", "duration_s": 1.5, "action": "react", "emotion": "surprised"},
        ],
    }


class TimelineTests(unittest.TestCase):
    def test_contiguous_timeline(self):
        shots = build_timeline(sample())
        self.assertEqual([(s.start_ms, s.end_ms) for s in shots],
                         [(0, 2500), (2500, 5500), (5500, 7000)])
        self.assertEqual(frame_state(shots, 2500)["speaker_id"], "orion")
        self.assertEqual(frame_state(shots, 7000)["progress"], 1.0)

    def test_deterministic(self):
        self.assertEqual(build_timeline(sample()), build_timeline(sample()))

    def test_unknown_speaker(self):
        plan = sample()
        plan["shots"][0]["speaker_id"] = "intruder"
        with self.assertRaises(ValueError):
            build_timeline(plan)

    def test_rejects_arbitrary_commands(self):
        plan = sample()
        plan["shots"][0]["action"] = "run_shell_command"
        with self.assertRaises(ValueError):
            build_timeline(plan)

    def test_rejects_invalid_durations(self):
        for value in (0, -1, True, float("nan"), float("inf"), 999):
            plan = sample()
            plan["shots"][0]["duration_s"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_timeline(plan)

    def test_rejects_duplicate_ids(self):
        plan = sample()
        plan["shots"][1]["id"] = "s1"
        with self.assertRaises(ValueError):
            build_timeline(plan)

    def test_rejects_oversize(self):
        plan = sample()
        plan["shots"] = plan["shots"] * 5
        with self.assertRaises(ValueError):
            build_timeline(plan)

    def test_frame_bounds(self):
        shots = build_timeline(sample())
        for value in (-1, 7001):
            with self.assertRaises(ValueError):
                frame_state(shots, value)


if __name__ == "__main__":
    unittest.main()
