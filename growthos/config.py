"""Environment configuration — Supabase connection settings.

Values are read lazily (at call time, not import time) so importing this
module never fails just because .env isn't loaded yet in a given context
(tests, tooling, etc).
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    anon_key: str
    service_role_key: str | None  # only set in trusted backend contexts


def load_supabase_config(require_service_role: bool = False) -> SupabaseConfig:
    url = os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    missing = [
        name for name, val in (("SUPABASE_URL", url), ("SUPABASE_ANON_KEY", anon_key))
        if not val
    ]
    if require_service_role and not service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(
            "variables d'environnement Supabase manquantes : " + ", ".join(missing)
        )

    return SupabaseConfig(url=url, anon_key=anon_key, service_role_key=service_role_key)
