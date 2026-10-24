"""Static guarantees about the files that can start an animation job: they must be impossible to start by accident."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = (ROOT / ".github" / "workflows" / "story-animation-worker.yml").read_text(encoding="utf-8")
MAIN_WORKFLOW = (ROOT / ".github" / "workflows" / "growthos-worker.yml").read_text(encoding="utf-8")
MIGRATION = (ROOT / "growthos" / "supabase" / "pending" / "story_packs_bucket.sql").read_text(encoding="utf-8")


def triggers(text: str) -> set:
    block = re.search(r"^on:\n((?:[ \t]+.*\n|\n)+)", text, re.M).group(1)
    return set(re.findall(r"^  ([a-z_]+):", block, re.M))


class DedicatedWorkflow(unittest.TestCase):
    def test_only_manual_dispatch_can_start_it(self):
        self.assertEqual(triggers(WORKFLOW), {"workflow_dispatch"})

    def test_job_is_skipped_unless_the_repository_variable_is_true(self):
        self.assertIn("if: ${{ vars.STORY_ANIMATION_ENABLED == 'true' }}", WORKFLOW)

    def test_read_only_permissions_and_single_run(self):
        self.assertIn("permissions:\n  contents: read", WORKFLOW)
        self.assertIn("group: story-animation-worker", WORKFLOW)
        self.assertIn("cancel-in-progress: false", WORKFLOW)

    def test_godot_download_is_checksum_verified(self):
        self.assertIn("sha512sum godot.zip", WORKFLOW)
        self.assertIn('test -n "$expected" && test "$expected" = "$actual"', WORKFLOW)

    def test_secrets_are_limited_to_what_an_animated_job_needs(self):
        used = set(re.findall(r"secrets\.([A-Z_]+)", WORKFLOW))
        self.assertEqual(used, {"SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "ELEVENLABS_API_KEY",
                                "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ADMIN_USER_IDS"})
        for forbidden in ("PEXELS", "CRON_SECRET", "SITE_URL", "YOUTUBE", "TIKTOK"):
            self.assertNotIn(forbidden, WORKFLOW)

    def test_pack_is_fetched_before_rendering(self):
        self.assertLess(WORKFLOW.index("cli fetch-pack"), WORKFLOW.index("run: python animation_worker.py"))

    def test_main_worker_never_receives_the_flag(self):
        self.assertNotIn("STORY_ANIMATION_ENABLED", MAIN_WORKFLOW)
        self.assertNotIn("GODOT", MAIN_WORKFLOW)


class PackBucketMigration(unittest.TestCase):
    def test_bucket_is_private_and_has_no_policy(self):
        self.assertIn("'story-packs', 'story-packs', false", MIGRATION)
        self.assertIn("update storage.buckets set public = false", MIGRATION)
        self.assertNotIn("create policy", MIGRATION.lower().replace("-- ", ""))

    def test_it_stays_in_pending(self):
        self.assertEqual(Path(ROOT / "growthos" / "supabase" / "pending" / "story_packs_bucket.sql").parent.name, "pending")
        self.assertFalse(list((ROOT / "growthos" / "supabase" / "migrations").glob("*story_packs*")))


if __name__ == "__main__":
    unittest.main()
