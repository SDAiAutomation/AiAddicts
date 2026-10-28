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
    def test_only_dispatch_and_schedule_can_start_it(self):
        self.assertEqual(triggers(WORKFLOW), {"workflow_dispatch", "schedule"})

    def test_schedule_is_offset_from_the_main_worker(self):
        self.assertIn('cron: "2,12,22,32,42,52 * * * *"', WORKFLOW)
        self.assertNotIn('"2,12,22,32,42,52', MAIN_WORKFLOW)

    def test_heavy_job_needs_work_and_the_repository_variable_is_an_off_switch(self):
        self.assertIn("if: ${{ vars.STORY_ANIMATION_ENABLED != 'false' }}", WORKFLOW)  # light check-queue job
        self.assertIn(
            "if: ${{ vars.STORY_ANIMATION_ENABLED != 'false' && needs.check-queue.outputs.has_work == 'true' }}", WORKFLOW
        )
    def test_read_only_permissions_and_single_run(self):
        self.assertIn("permissions:\n  contents: read", WORKFLOW)
        self.assertIn("group: story-animation-worker", WORKFLOW)
        self.assertIn("cancel-in-progress: false", WORKFLOW)

    def test_godot_download_is_checked_against_a_hash_pinned_in_the_repository(self):
        self.assertIn("sha512sum godot.zip", WORKFLOW)
        self.assertIn('test -n "$GODOT_ZIP_SHA512" && test "$GODOT_ZIP_SHA512" = "$actual"', WORKFLOW)
        pinned = re.search(r"GODOT_ZIP_SHA512: ([0-9a-f]+)", WORKFLOW)
        self.assertIsNotNone(pinned)
        self.assertEqual(len(pinned.group(1)), 128)                 # a SHA-512 digest, not a placeholder
        self.assertNotIn("SHA512-SUMS.txt\"", WORKFLOW)             # the sum is no longer fetched from the archive's own origin

    def test_godot_runs_in_an_empty_network_namespace_without_root_and_the_job_proves_it_first(self):
        self.assertIn("unshare -n setpriv", WORKFLOW)
        self.assertIn("--clear-groups xvfb-run", WORKFLOW)
        self.assertNotIn("STORY_RENDER_LAUNCHER: ", WORKFLOW)       # only the isolated launcher written by the step may be used
        self.assertLess(WORKFLOW.index('test "$out" = "ISOLATED uid='), WORKFLOW.index("python animation_worker.py"))
        self.assertLess(WORKFLOW.index("Isolate the renderer"), WORKFLOW.index("Render the queued animated jobs"))

    def test_the_secret_free_benchmark_renders_through_the_same_isolation(self):
        bench = (ROOT / ".github" / "workflows" / "story-animation-render-benchmark.yml").read_text(encoding="utf-8")
        self.assertIn("unshare -n setpriv", bench)
        self.assertIn('--launcher "$STORY_RENDER_LAUNCHER"', bench)

    def test_every_third_party_action_is_pinned_to_a_commit(self):
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", WORKFLOW, re.M)
        self.assertTrue(uses)
        for ref in uses:
            self.assertRegex(ref, r"@[0-9a-f]{40}$", f"{ref} must be pinned to a full commit SHA")

    def test_the_job_runs_in_a_protected_environment(self):
        self.assertIn("environment: story-animation", WORKFLOW)

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
