"""Phase 2.6 (benchmark fixes) — style-preserving fallback for AI-image
styles, the deterministic style-integrity signal, and fallback observability.
Reproduces the concrete defect the visual benchmark found: a single OpenAI
moderation rejection silently swapping a `cinematic_real` scene for an
unrelated Pexels stock photo, breaking style/character continuity.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import visuals


class TestNearestFallbackSources(unittest.TestCase):
    def test_prefers_previous_then_next(self):
        sources = visuals._nearest_fallback_sources([None, "a.jpg", None, None, "e.jpg"])
        self.assertEqual(sources, {0: 1, 2: 1, 3: 4})

    def test_no_available_source_returns_empty(self):
        self.assertEqual(visuals._nearest_fallback_sources([None, None]), {})

    def test_nothing_missing_returns_empty(self):
        self.assertEqual(visuals._nearest_fallback_sources(["a.jpg", "b.jpg"]), {})


class TestStyleIntegrityPreserved(unittest.TestCase):
    def test_pexels_photo_breaks_an_ai_image_identity_style(self):
        for profile in ("cinematic", "gentle", "energetic", "comic"):
            self.assertFalse(
                visuals.is_style_integrity_preserved(profile, "/work/images/block-06.jpg"),
                f"profile {profile!r} should flag a Pexels photo fallback",
            )

    def test_reusing_another_scene_preserves_identity(self):
        self.assertTrue(visuals.is_style_integrity_preserved("cinematic", "/work/images/scene-02.jpg"))

    def test_kinetic_and_none_profiles_have_no_identity_to_break(self):
        self.assertTrue(visuals.is_style_integrity_preserved("kinetic", "/work/images/block-06.jpg"))
        self.assertTrue(visuals.is_style_integrity_preserved("none", "/work/images/block-06.jpg"))

    def test_missing_asset_is_not_flagged_as_style_broken(self):
        self.assertTrue(visuals.is_style_integrity_preserved("cinematic", None))


def _blocks():
    return [
        {"role": "hook", "text": "un", "visual": "un chat noir assis sur un mur", "shotType": "close_up"},
        {"role": "point", "text": "deux", "visual": "un chien qui court dans un champ", "shotType": "wide"},
        {"role": "cta", "text": "trois", "visual": "un oiseau bleu sur une branche", "shotType": "medium"},
    ]


def _write_fake_jpeg(out_path: str) -> str:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(b"fake-jpeg-bytes")
    return out_path


class TestFetchBlockImagesStylePreservingFallback(unittest.TestCase):
    """The benchmark's actual failure mode: OpenAI moderation rejects ONE
    scene of an AI-image-style video. Before Phase 2.6, the next step tried
    a Pexels photo search for that block, swapping in unrelated stock
    footage mid-video. After: the block reuses another scene from the SAME
    video, and the event is recorded with its real failure reason."""

    def _run(self, *, pexels_key: str | None):
        def fake_generate(prompt, out_path, aspect_ratio, ref, model, quality):
            # Le bloc "chien" (index 1) échoue systématiquement, quel que
            # soit l'ordre d'exécution du pool de threads.
            if "chien" in prompt:
                return None
            return _write_fake_jpeg(out_path)

        with tempfile.TemporaryDirectory() as tmp:
            env = {"OPENAI_API_KEY": "test-key", "IMAGE_QC_ENABLED": "false"}
            with patch.dict(os.environ, env), \
                 patch("engine.visuals.openai_images.generate_image", side_effect=fake_generate), \
                 patch("engine.visuals.openai_images.pop_last_usage", return_value=None), \
                 patch("engine.visuals.openai_images.pop_last_error", return_value="content_policy"):
                return visuals.fetch_block_images(
                    _blocks(), None, "9:16", Path(tmp), pexels_key, visual_style="cinematic_real",
                )

    def test_failed_scene_reuses_same_video_scene_never_pexels(self):
        paths, _reports, fallbacks, _treatments = self._run(pexels_key="pexels-key-present")
        self.assertIsNotNone(paths[1])
        self.assertNotIn("block-", Path(paths[1]).name)  # jamais une photo Pexels
        self.assertTrue(Path(paths[1]).name.startswith("scene-"))

    def test_reused_scene_comes_from_the_same_video(self):
        paths, _reports, _fallbacks, _treatments = self._run(pexels_key=None)
        self.assertIn(paths[1], (paths[0], paths[2]))

    def test_fallback_event_metadata_is_recorded(self):
        _paths, _reports, fallbacks, _treatments = self._run(pexels_key=None)
        self.assertEqual(len(fallbacks), 1)
        event = fallbacks[0]
        self.assertEqual(event["blockIndex"], 1)
        self.assertEqual(event["requestedVisualStyle"], "cinematic_real")
        self.assertEqual(event["assetStrategy"], "ai_image")
        self.assertEqual(event["failureType"], "content_policy")
        self.assertEqual(event["fallbackStrategy"], "reuse_same_video_scene")
        self.assertIn(event["fallbackSource"], (0, 2))
        self.assertTrue(event["styleIntegrityPreserved"])

    def test_no_pexels_attempt_even_when_a_pexels_key_is_configured(self):
        # Avant Phase 2.6 : une clé Pexels présente déclenchait quand même
        # une recherche stock pour le bloc en échec. Plus maintenant : OpenAI
        # configuré = stratégie principale, Pexels n'est jamais tenté ici.
        with tempfile.TemporaryDirectory() as tmp:
            env = {"OPENAI_API_KEY": "test-key", "IMAGE_QC_ENABLED": "false"}
            with patch.dict(os.environ, env), \
                 patch("engine.visuals.openai_images.generate_image", return_value=None), \
                 patch("engine.visuals.openai_images.pop_last_error", return_value="content_policy"), \
                 patch("engine.visuals.search_image_url") as mock_pexels_search:
                visuals.fetch_block_images(
                    _blocks(), None, "9:16", Path(tmp), "pexels-key-present", visual_style="cinematic_real",
                )
            mock_pexels_search.assert_not_called()

    def test_all_scenes_failing_falls_back_to_flat_color_not_pexels(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"OPENAI_API_KEY": "test-key", "IMAGE_QC_ENABLED": "false"}
            with patch.dict(os.environ, env), \
                 patch("engine.visuals.openai_images.generate_image", return_value=None), \
                 patch("engine.visuals.openai_images.pop_last_error", return_value="server_error"), \
                 patch("engine.visuals.search_image_url") as mock_pexels_search:
                paths, _reports, fallbacks, _treatments = visuals.fetch_block_images(
                    _blocks(), None, "9:16", Path(tmp), "pexels-key-present", visual_style="cinematic_real",
                )
            self.assertEqual(paths, [None, None, None])
            self.assertEqual(fallbacks, [])  # rien à réutiliser -> pas d'évènement, fond uni côté video.py
            mock_pexels_search.assert_not_called()


class TestFetchBlockImagesUnaffectedPaths(unittest.TestCase):
    def test_stock_footage_style_returns_a_four_tuple_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths, reports, fallbacks, treatments = visuals.fetch_block_images(
                _blocks(), None, "9:16", Path(tmp), None, visual_style="stock_footage",
            )
            self.assertEqual(paths, [None, None, None])  # pas de clé Pexels -> fond uni
            self.assertEqual(reports, [])
            self.assertEqual(fallbacks, [])
            self.assertEqual(treatments, [])

    def test_no_openai_key_uses_pexels_as_primary_strategy_not_fallback(self):
        # OpenAI absent : Pexels EST la stratégie principale de cette vidéo,
        # pas un repli d'identité — une réutilisation entre blocs Pexels ne
        # doit pas être signalée comme cassant un style.
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OPENAI_API_KEY", None)
                with patch("engine.visuals.search_image_url", return_value=None):
                    paths, _reports, fallbacks, _treatments = visuals.fetch_block_images(
                        _blocks(), None, "9:16", Path(tmp), None, visual_style="cinematic_real",
                    )
            self.assertEqual(paths, [None, None, None])
            self.assertEqual(fallbacks, [])


if __name__ == "__main__":
    unittest.main()
