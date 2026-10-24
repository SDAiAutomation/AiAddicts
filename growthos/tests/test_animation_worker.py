import os
import unittest
from unittest.mock import Mock, patch

import animation_worker


class FlagOff(unittest.TestCase):
    def test_nothing_is_claimed_and_no_client_is_created(self):
        with patch.dict(os.environ, {}), patch("animation_worker.db.get_service_client") as client, patch("animation_worker.claim.claim_animated_item") as claim:
            os.environ.pop("STORY_ANIMATION_ENABLED", None)
            with patch("sys.argv", ["animation_worker.py", "--until-idle"]):
                self.assertEqual(animation_worker.main(), 0)
        client.assert_not_called()
        claim.assert_not_called()


class ProcessOne(unittest.TestCase):
    def test_empty_queue(self):
        with patch("animation_worker.claim.claim_animated_item", return_value=None), patch("animation_worker.assembler.run_for_content_item") as run:
            self.assertFalse(animation_worker.process_one(Mock()))
        run.assert_not_called()

    def test_success(self):
        with patch("animation_worker.claim.claim_animated_item", return_value={"id": "item"}), \
                patch("animation_worker.assembler.run_for_content_item", return_value={"video_url": "u"}) as run, \
                patch("animation_worker.repo.mark_failed") as failed:
            self.assertTrue(animation_worker.process_one(Mock()))
        run.assert_called_once_with("item")
        failed.assert_not_called()

    def test_failure_marks_the_job_and_continues(self):
        with patch("animation_worker.claim.claim_animated_item", return_value={"id": "item"}), \
                patch("animation_worker.assembler.run_for_content_item", side_effect=RuntimeError("boom")), \
                patch("animation_worker.repo.mark_failed") as failed, \
                patch("animation_worker.events.record") as record, \
                patch("animation_worker.events.organization_id_of", return_value="org"):
            self.assertTrue(animation_worker.process_one(Mock()))
        failed.assert_called_once()
        self.assertEqual(failed.call_args.args[1:], ("item", "boom"))
        self.assertEqual(record.call_args.args[1], "generation_failed")

    def test_only_one_pass_with_once(self):
        calls = []
        with patch.dict(os.environ, {"STORY_ANIMATION_ENABLED": "1"}), patch("animation_worker.db.get_service_client", return_value=Mock()), \
                patch("animation_worker.process_one", side_effect=lambda c: calls.append(1) or True), patch("sys.argv", ["animation_worker.py", "--once"]):
            self.assertEqual(animation_worker.main(), 0)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
