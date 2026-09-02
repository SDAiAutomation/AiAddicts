import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_supabase_config

ENV_KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")


class TestLoadSupabaseConfig(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_missing_vars_raise_with_clear_message(self):
        with self.assertRaises(RuntimeError) as ctx:
            load_supabase_config()
        self.assertIn("SUPABASE_URL", str(ctx.exception))
        self.assertIn("SUPABASE_ANON_KEY", str(ctx.exception))

    def test_valid_config_loads(self):
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = "anon-key"
        cfg = load_supabase_config()
        self.assertEqual(cfg.url, "https://example.supabase.co")
        self.assertIsNone(cfg.service_role_key)

    def test_require_service_role_raises_when_absent(self):
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_ANON_KEY"] = "anon-key"
        with self.assertRaises(RuntimeError) as ctx:
            load_supabase_config(require_service_role=True)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
