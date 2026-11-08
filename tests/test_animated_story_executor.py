from pathlib import Path
import pytest
from growthos.engine.animated_story import Character, Shot, Story
from growthos.engine.animated_story_plan import plan_render
from growthos.engine.animated_story_executor import execute_plan, ExistingClipRenderer

def make_plan(dialogue=""):
    story = Story("story", "pilot",
        (Character("fox", "Fox", "asset", "voice"),),
        (Shot("shot1", 3, "action", ("fox",), "room",
              dialogue=dialogue, speaker_id="fox" if dialogue else None),))
    return plan_render(story, video_usd_per_second=0, tts_usd_per_character=0)

def test_existing_clip_renders_and_reuses_cache(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"mock video")
    plan = make_plan()
    renderer = ExistingClipRenderer({"shot1": source})
    first = execute_plan(plan, tmp_path / "out", shot_renderer=renderer)
    source.unlink()
    second = execute_plan(plan, tmp_path / "out", shot_renderer=renderer)
    assert first == second
    assert first[0].video_path.read_bytes() == b"mock video"

def test_missing_clip_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="missing_clip"):
        execute_plan(make_plan(), tmp_path / "out",
                     shot_renderer=ExistingClipRenderer({}))

def test_voice_requires_explicit_authorization(tmp_path):
    class Voice:
        def render(self, text, voice_id, output_path):
            raise AssertionError("must not call provider")
    with pytest.raises(PermissionError, match="paid_voice"):
        execute_plan(make_plan("Hello"), tmp_path / "out",
                     shot_renderer=ExistingClipRenderer({}), voice_renderer=Voice())

def test_voice_requires_budget_hook(tmp_path):
    class Voice:
        def render(self, text, voice_id, output_path):
            raise AssertionError("must not call provider")
    with pytest.raises(PermissionError, match="budget_guard"):
        execute_plan(make_plan("Hello"), tmp_path / "out",
                     shot_renderer=ExistingClipRenderer({}), voice_renderer=Voice(),
                     authorize_paid_calls=True)
