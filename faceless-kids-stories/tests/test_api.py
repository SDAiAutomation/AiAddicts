import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
from engine.jobs import JobStatus  # noqa: E402


def _fake_generate_story(story_path, on_progress=None):
    if on_progress:
        on_progress("voiceover", "bloc 1/1")
    return Path(story_path).parent / "fake_final.mp4"


class TestApi(unittest.TestCase):
    def setUp(self):
        # Le context manager déclenche les événements lifespan (démarrage du worker).
        self.client = TestClient(api.app)
        self.client.__enter__()
        self.addCleanup(lambda: self.client.__exit__(None, None, None))

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_list_stories_includes_sample(self):
        resp = self.client.get("/stories")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("histoire-01.json", resp.json())

    def test_create_job_missing_story_returns_404(self):
        resp = self.client.post("/jobs", json={"story_path": "stories/does-not-exist.json"})
        self.assertEqual(resp.status_code, 404)

    def test_get_unknown_job_returns_404(self):
        resp = self.client.get("/jobs/job_999999")
        self.assertEqual(resp.status_code, 404)

    @patch("engine.worker.generate_story", side_effect=_fake_generate_story)
    def test_job_lifecycle_completes(self, _mock):
        resp = self.client.post("/jobs", json={"story_path": "stories/histoire-01.json"})
        self.assertEqual(resp.status_code, 201)
        job = resp.json()
        self.assertEqual(job["status"], JobStatus.PENDING.value)

        job_id = job["id"]
        deadline = time.monotonic() + 5
        final_status = None
        while time.monotonic() < deadline:
            status_resp = self.client.get(f"/jobs/{job_id}")
            self.assertEqual(status_resp.status_code, 200)
            final_status = status_resp.json()
            if final_status["status"] in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                break
            time.sleep(0.05)

        self.assertIsNotNone(final_status)
        self.assertEqual(final_status["status"], JobStatus.COMPLETED.value)
        self.assertTrue(final_status["result_path"].endswith("fake_final.mp4"))

    @patch("engine.worker.generate_story", side_effect=RuntimeError("panne simulée"))
    def test_job_lifecycle_failure_is_reported(self, _mock):
        resp = self.client.post("/jobs", json={"story_path": "stories/histoire-01.json"})
        job_id = resp.json()["id"]

        deadline = time.monotonic() + 5
        final_status = None
        while time.monotonic() < deadline:
            status_resp = self.client.get(f"/jobs/{job_id}")
            final_status = status_resp.json()
            if final_status["status"] in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                break
            time.sleep(0.05)

        self.assertEqual(final_status["status"], JobStatus.FAILED.value)
        self.assertIn("panne simulée", final_status["error"])

    def test_list_jobs_returns_created_jobs(self):
        resp = self.client.post("/jobs", json={"story_path": "stories/histoire-01.json"})
        job_id = resp.json()["id"]
        list_resp = self.client.get("/jobs")
        self.assertEqual(list_resp.status_code, 200)
        ids = [job["id"] for job in list_resp.json()]
        self.assertIn(job_id, ids)


if __name__ == "__main__":
    unittest.main()
