"""The Story Visual pilot workflow is isolated from production by construction: manual trigger only, a dedicated environment, test-only secrets,
a production-database guard, a confirmation plus an arming variable before anything paid, and a single place where the flag is set."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "story-visual-pilot-worker.yml").read_text(encoding="utf-8")
PRODUCTION = (ROOT / ".github" / "workflows" / "growthos-worker.yml").read_text(encoding="utf-8")
BODY = "\n".join(line for line in WORKFLOW.splitlines() if not line.lstrip().startswith("#"))  # comments may name what is forbidden
PROD_REF = "lclesqfokgetznhepgmj"


def step(title: str) -> str:
    """Text of the step whose name starts with `title` (up to the next step)."""
    start = BODY.index(f"- name: {title}")
    nxt = [m.start() for m in re.finditer(r"\n      - (?:name|uses):", BODY[start + 10:])]
    return BODY[start: start + 10 + nxt[0]] if nxt else BODY[start:]


class TestTriggers(unittest.TestCase):
    def test_manual_dispatch_only(self):
        self.assertIn("workflow_dispatch:", BODY)
        for forbidden in ("schedule:", "push:", "pull_request", "workflow_run", "repository_dispatch", "cron:"):
            self.assertNotIn(forbidden, BODY)

    def test_runs_only_from_the_default_branch_of_this_repository_in_its_own_environment(self):
        self.assertIn("github.repository == 'SDAiAutomation/AiAddicts'", BODY)
        self.assertIn("github.ref == 'refs/heads/growthos/mvp'", BODY)
        self.assertIn("environment: story-visual-pilot", BODY)
        self.assertRegex(BODY, r"permissions:\n  contents: read\n")
        self.assertRegex(BODY, r"concurrency:\n  group: story-visual-pilot\n  cancel-in-progress: false")
        self.assertLessEqual(int(re.search(r"timeout-minutes: (\d+)", BODY).group(1)), 30)

    def test_default_mode_is_the_free_preflight(self):
        self.assertRegex(BODY, r"mode:\n(?:.*\n)*?        default: preflight")


class TestSecretsAndIsolation(unittest.TestCase):
    def test_only_test_secrets_and_variables_are_referenced(self):
        secrets = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", BODY))
        self.assertEqual(secrets, {"PILOT_SUPABASE_URL", "PILOT_SUPABASE_ANON_KEY", "PILOT_SUPABASE_SERVICE_ROLE_KEY", "PILOT_OPENAI_API_KEY",
                                   "PILOT_ELEVENLABS_API_KEY", "PILOT_ADMIN_USER_IDS"})
        for name in re.findall(r"vars\.([A-Za-z0-9_]+)", BODY):
            self.assertTrue(name.startswith("PILOT_"), name)
        for production_name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ADMIN_USER_IDS", "CRON_SECRET", "SITE_URL", "PEXELS", "ANTHROPIC"):
            self.assertNotRegex(BODY, rf"secrets\.{production_name}\b")  # the production secrets are never referenced (no silent fallback to production)

    def test_the_production_database_is_refused_before_anything_else_runs(self):
        guard = step("Refuse the production database")
        self.assertIn(PROD_REF, guard)
        self.assertIn("https://*", guard)
        for name in ("PILOT_SUPABASE_URL", "PILOT_SUPABASE_ANON_KEY", "PILOT_SUPABASE_SERVICE_ROLE_KEY", "PILOT_ADMIN_USER_IDS"):
            self.assertIn(name, guard)
        self.assertLess(BODY.index("Refuse the production database"), BODY.index("actions/setup-python"))
        self.assertLess(BODY.index("Refuse the production database"), BODY.index("Pre-flight"))
        self.assertNotIn(PROD_REF, "".join(re.findall(r"vars\.[A-Z_]+", BODY)))

    def test_the_production_worker_never_sees_the_pilot_secrets_or_environment(self):
        for text in ("PILOT_", "story-visual-pilot"):
            self.assertNotIn(text, PRODUCTION)

    def test_the_production_worker_gets_the_flag_only_from_a_repository_variable_never_hard_coded(self):
        """Owner decision (2026-11-06): the production worker may run Story Visual PLANNING (admin only, <= 1 USD, no render without the
        site's separate generation flag). The flag stays OFF by default: it comes from the repository variable, which is empty until the
        owner sets it, and it is never written in the workflow. The pilot worker stays the only place that sets it to a literal."""
        lines = [line.strip() for line in PRODUCTION.splitlines() if "STORY_VISUAL_ENABLED" in line and not line.strip().startswith("#")]
        self.assertEqual(lines, ["STORY_VISUAL_ENABLED: ${{ vars.STORY_VISUAL_ENABLED }}"])
        for name in ("STORY_PLANNER_MODEL", "STORY_PLAN_INPUT_TOKEN_CEILING", "STORY_PLAN_MAX_OUTPUT_TOKENS"):
            self.assertRegex(PRODUCTION, rf"{name}: \$\{{\{{ vars\.{name} \}}\}}")
        self.assertNotIn("STORY_VISUAL_GENERATION_ENABLED", PRODUCTION)  # the paid generation flag is not wired here

    def test_the_production_worker_renders_an_illustrated_story_with_the_measured_image_settings_and_a_one_dollar_cap(self):
        """Owner decision (2026-11-06): the render uses DEDICATED image variables (the measured combination), never the shared ones that
        every other style reads, and the episode budget is capped at 1 USD (the engine default is 2)."""
        def value(name):
            match = re.search(rf'^\s+{name}: "([^"]*)"', PRODUCTION, re.MULTILINE)
            self.assertIsNotNone(match, name)
            return match.group(1)
        self.assertEqual((value("STORY_VISUAL_IMAGE_MODEL"), value("STORY_VISUAL_IMAGE_QUALITY")), ("gpt-image-2.5-flare", "low"))
        self.assertGreaterEqual(float(value("STORY_IMAGE_USD_EACH")), 0.0092)  # never below the measured cost
        self.assertEqual((value("STORY_RENDER_USD"), value("STORY_STORAGE_USD")), ("0", "0.01"))
        self.assertLessEqual(float(value("STORY_BUDGET_USD")), 1.0)
        self.assertLessEqual(float(value("STORY_BUDGET_PREFERRED_USD")), float(value("STORY_BUDGET_USD")))
        self.assertRegex(PRODUCTION, r"STORY_DEFAULT_VOICE_ID: \$\{\{ vars\.STORY_DEFAULT_VOICE_ID \}\}")
        for shared in ("IMAGE_MODEL_PREMIUM", "IMAGE_FINAL_QUALITY", "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_QUALITY"):
            self.assertNotIn(shared, PRODUCTION)  # the other styles keep their own defaults


class TestNothingPaidWithoutAuthorisation(unittest.TestCase):
    def test_run_mode_needs_the_exact_confirmation_and_the_arming_variable(self):
        confirm = step("Confirm the paid operation")
        self.assertIn("if: ${{ inputs.mode == 'run' }}", confirm)
        self.assertIn('"$CONFIRM" != "RUN-PAID-PILOT"', confirm)
        self.assertIn('"$ARMED" != "true"', confirm)
        self.assertIn("vars.PILOT_WORKER_ARMED", confirm)
        self.assertLess(BODY.index("Confirm the paid operation"), BODY.index("Run ONE pilot episode"))

    def test_the_flag_is_set_in_one_place_only_the_paid_step(self):
        self.assertEqual(len(re.findall(r"STORY_VISUAL_ENABLED", BODY)), 1)
        paid = step("Run ONE pilot episode")
        self.assertIn('STORY_VISUAL_ENABLED: "1"', paid)
        self.assertIn("if: ${{ inputs.mode == 'run' }}", paid)
        self.assertNotIn("STORY_VISUAL_ENABLED", step("Pre-flight"))

    def test_the_worker_runs_at_most_one_job_and_only_in_the_paid_step(self):
        commands = re.findall(r"python worker\.py[^\n]*", BODY)
        self.assertEqual(commands, ["python worker.py --once"])
        self.assertNotIn("--until-idle", BODY)
        self.assertIn("python worker.py --once", step("Run ONE pilot episode"))

    def test_the_preflight_is_offline_and_comes_before_the_paid_step(self):
        pre = step("Pre-flight")
        self.assertIn("python scripts/story_visual_pilot_preflight.py --max-usd 1.0", pre)
        self.assertNotIn("worker.py", pre)
        self.assertLess(BODY.index("Pre-flight"), BODY.index("Run ONE pilot episode"))  # a failing pre-flight stops the job before the paid step

    def test_the_caps_and_the_measured_model_are_fixed_in_the_file_not_in_variables(self):
        for block in (step("Pre-flight"), step("Run ONE pilot episode")):
            for line in ('STORY_BUDGET_USD: "1.00"', 'STORY_BUDGET_PREFERRED_USD: "0.50"', 'STORY_VISUAL_MAX_JOBS_PER_DAY: "1"', "IMAGE_MODEL_PREMIUM: gpt-image-2.5-flare",
                         "IMAGE_FINAL_QUALITY: low", 'SCRIPT_PRICE_IN_PER_M: "0"', 'STORY_PLAN_TOKENS_OUT: "0"'):
                self.assertIn(line, block)
            # the tariffs the owner must confirm come from environment variables and have NO default: unset stays unset (the pre-flight then blocks)
            self.assertIn("${{ vars.PILOT_ELEVENLABS_USD_PER_1K_CHARS }}", block)
            self.assertNotRegex(block, r"vars\.PILOT_[A-Z_]+ \|\|")

    def test_no_planner_key_and_no_artifact_upload(self):
        for forbidden in ("ANTHROPIC", "PEXELS", "upload-artifact", "actions/cache"):
            self.assertNotIn(forbidden, BODY)


if __name__ == "__main__":
    unittest.main()
