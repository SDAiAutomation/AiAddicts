import pytest
from growthos.engine.animated_story import Character, Shot, Story
from growthos.engine.animated_story_plan import RenderPlanError, plan_render

def story(dialogue="Hello"):
    return Story(
        "episode", "Pilot",
        (Character("fox", "Fox", "asset1", "voice1", ("blue coat",)),),
        (Shot("s1", 3, "dialogue", ("fox",), "room",
              dialogue=dialogue, speaker_id="fox", reference_frame_id="frame1"),),
    )

def test_plan_is_deterministic():
    a = plan_render(story(), video_usd_per_second=.1, tts_usd_per_character=.001)
    b = plan_render(story(), video_usd_per_second=.1, tts_usd_per_character=.001)
    assert a == b
    assert a.tasks[0].speaker_voice_id == "voice1"

def test_dialogue_changes_cache_key():
    a = plan_render(story("Hello"), video_usd_per_second=.1, tts_usd_per_character=.001)
    b = plan_render(story("Goodbye"), video_usd_per_second=.1, tts_usd_per_character=.001)
    assert a.tasks[0].cache_key != b.tasks[0].cache_key

def test_budget_fails_closed():
    with pytest.raises(RenderPlanError, match="budget_exceeded"):
        plan_render(story(), video_usd_per_second=1, tts_usd_per_character=.001, max_budget_usd=1)

def test_negative_rate_rejected():
    with pytest.raises(RenderPlanError, match="invalid_budget"):
        plan_render(story(), video_usd_per_second=-1, tts_usd_per_character=0)
