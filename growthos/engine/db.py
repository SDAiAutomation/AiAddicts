"""Supabase client factory.

Two distinct trust levels, on purpose (see the security docs' least-privilege
principle):

- get_client(): anon key, subject to RLS. Safe for anything that acts on
  behalf of a signed-in user.
- get_service_client(): service_role key, BYPASSES RLS entirely. Backend-only
  (writing audit.events, crediting/debiting accounts, admin jobs). Never
  import this from anything reachable by end-user input.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_supabase_config


def get_client():
    from supabase import create_client

    cfg = load_supabase_config()
    return create_client(cfg.url, cfg.anon_key)


def get_service_client():
    from supabase import create_client

    cfg = load_supabase_config(require_service_role=True)
    return create_client(cfg.url, cfg.service_role_key)
