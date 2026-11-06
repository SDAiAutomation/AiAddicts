"""Le modèle et la qualité d'un récit illustré viennent de variables dédiées, sans changer les réglages communs aux autres styles."""
import os
import unittest
from unittest.mock import patch

from growthos.engine import image_model_router
from growthos.engine.story_visual import orchestrator

SHARED = {"IMAGE_MODEL_PREMIUM": "shared-model", "IMAGE_FINAL_QUALITY": "high"}
NAMES = ("STORY_VISUAL_IMAGE_MODEL", "STORY_VISUAL_IMAGE_QUALITY", "IMAGE_MODEL_PREMIUM", "IMAGE_FINAL_QUALITY", "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_QUALITY")


def clean(**extra):
    env = {k: v for k, v in os.environ.items() if k not in NAMES}
    env.update(extra)
    return patch.dict(os.environ, env, clear=True)


class TestImageSelection(unittest.TestCase):
    def test_dedicated_variables_win_over_the_shared_ones(self):
        with clean(**SHARED, STORY_VISUAL_IMAGE_MODEL="gpt-image-2.5-flare", STORY_VISUAL_IMAGE_QUALITY="low"):
            picked = orchestrator.image_selection()
            self.assertEqual((picked.model, picked.quality, picked.purpose), ("gpt-image-2.5-flare", "low", "final"))
            # the other styles keep reading the shared settings, untouched
            shared = image_model_router.select_model("final")
            self.assertEqual((shared.model, shared.quality), ("shared-model", "high"))

    def test_without_dedicated_variables_it_falls_back_to_the_router_exactly_as_before(self):
        with clean(**SHARED):
            picked, shared = orchestrator.image_selection(), image_model_router.select_model("final")
            self.assertEqual((picked.model, picked.quality), (shared.model, shared.quality))
        with clean():
            picked, shared = orchestrator.image_selection(), image_model_router.select_model("final")
            self.assertEqual((picked.model, picked.quality), (shared.model, shared.quality))

    def test_blank_or_unknown_values_never_become_a_model_or_quality(self):
        with clean(**SHARED, STORY_VISUAL_IMAGE_MODEL="   ", STORY_VISUAL_IMAGE_QUALITY="ultra"):
            picked = orchestrator.image_selection()
            self.assertEqual((picked.model, picked.quality), ("shared-model", "high"))
        with clean(STORY_VISUAL_IMAGE_QUALITY=" LOW "):
            self.assertEqual(orchestrator.image_selection().quality, "low")


if __name__ == "__main__":
    unittest.main()
