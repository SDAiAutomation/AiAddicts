"""Smoke tests for the isolated WOW animation experiment."""
import importlib.util
from pathlib import Path
import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'growthos' / 'experiments' / 'wow_offline_pilot.py'


def load_module():
    spec = importlib.util.spec_from_file_location('wow_offline_pilot', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frame_dimensions():
    module = load_module()
    assert module.frame_at(0).size == (540, 960)
    assert module.frame_at(150).mode == 'RGB'


def test_reject_invalid_render_args(tmp_path):
    module = load_module()
    with pytest.raises(ValueError): module.render(tmp_path / 'bad.mp4', duration=0)
    with pytest.raises(ValueError): module.render(tmp_path / 'bad.mp4', fps=0)


def test_scene_boundaries():
    module = load_module()
    assert len(module.SCENES) == 3
    assert module.SCENES[0][0] == 0
    assert module.SCENES[-1][1] == 15
