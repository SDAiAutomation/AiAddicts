import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import image_model_router

_ROUTER_ENV_VARS = (
    "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_QUALITY",
    "IMAGE_MODEL_FAST", "IMAGE_MODEL_PREMIUM", "IMAGE_MODEL_EDIT",
    "IMAGE_PREVIEW_QUALITY", "IMAGE_FINAL_QUALITY", "IMAGE_EDIT_QUALITY",
)


class TestSelectModel(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.pop(name, None) for name in _ROUTER_ENV_VARS}

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_final_defaults_match_legacy_env_vars_when_unset(self):
        # Aucune nouvelle variable renseignée : "final" doit retomber sur
        # exactement le comportement actuel (aucun changement de coût par défaut).
        selection = image_model_router.select_model("final")
        self.assertEqual(selection.model, "gpt-image-2.5-flare")
        self.assertEqual(selection.quality, "medium")

    def test_final_respects_legacy_env_vars_when_set(self):
        os.environ["OPENAI_IMAGE_MODEL"] = "gpt-image-1"
        os.environ["OPENAI_IMAGE_QUALITY"] = "high"
        selection = image_model_router.select_model("final")
        self.assertEqual(selection.model, "gpt-image-1")
        self.assertEqual(selection.quality, "high")

    def test_new_env_vars_override_legacy_for_final(self):
        os.environ["OPENAI_IMAGE_MODEL"] = "gpt-image-1-mini"
        os.environ["IMAGE_MODEL_PREMIUM"] = "gpt-image-1"
        os.environ["IMAGE_FINAL_QUALITY"] = "high"
        selection = image_model_router.select_model("final")
        self.assertEqual(selection.model, "gpt-image-1")
        self.assertEqual(selection.quality, "high")

    def test_preview_defaults(self):
        selection = image_model_router.select_model("preview")
        self.assertEqual(selection.model, "gpt-image-2.5-flare")
        self.assertEqual(selection.quality, "low")

    def test_edit_defaults_to_gpt_image_2_5_flare_high(self):
        selection = image_model_router.select_model("edit")
        self.assertEqual(selection.model, "gpt-image-2.5-flare")
        self.assertEqual(selection.quality, "high")

    def test_unknown_purpose_raises(self):
        with self.assertRaises(ValueError):
            image_model_router.select_model("ultra")


class TestEstimateCost(unittest.TestCase):
    def test_known_combo_returns_positive_cost(self):
        self.assertGreater(image_model_router.estimate_cost("gpt-image-1-mini", "medium"), 0)

    def test_unknown_combo_returns_zero(self):
        self.assertEqual(image_model_router.estimate_cost("modele-inconnu", "medium"), 0.0)


if __name__ == "__main__":
    unittest.main()
