from growthos.engine.animated_story import Character, Shot, Story, validate_story

def _story(**overrides):
    payload = dict(
        id="episode-1", title="The choice",
        characters=(Character("fox", "Fox", "ref-fox", "voice-fox"),),
        shots=(Shot("shot-1", 4, "dialogue", ("fox",), "room",
                    dialogue="Why?", speaker_id="fox", reference_frame_id="frame-1"),),
    )
    payload.update(overrides)
    return Story(**payload)

def test_valid_story():
    result = validate_story(_story())
    assert result.approved
    assert result.estimated_duration_seconds == 4

def test_rejects_unknown_character():
    story = _story(shots=(Shot("s1", 4, "dialogue", ("unknown",), "room",
                              dialogue="Hello", speaker_id="unknown"),))
    result = validate_story(story)
    assert not result.approved
    assert "unknown_character:s1" in result.errors

def test_rejects_missing_speaker():
    story = _story(shots=(Shot("s1", 3, "dialogue", ("fox",), "room", dialogue="Hello"),))
    assert "missing_speaker:s1" in validate_story(story).errors

def test_rejects_overlong_story():
    shots = tuple(Shot(f"s{i}", 10, "action", ("fox",), "room") for i in range(10))
    assert "duration_exceeded" in validate_story(_story(shots=shots)).errors
