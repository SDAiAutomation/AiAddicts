"""Autorisation de campagne : l'unique porte par laquelle un appel fournisseur RÉEL pourra un jour être permis.

Le propriétaire écrit un fichier `authorization.json` (modèle : `fixtures/p0d/authorization.template.json`, volontairement INVALIDE). Rien dans le code
ne le crée, ne le complète ni ne le devine. Une autorisation valide lie : la campagne, le modèle, l'hôte unique du fournisseur, un tarif DATÉ et
sourcé, un plafond monétaire dur, un nombre maximal d'appels, une fenêtre de temps, les empreintes du corpus et de la baseline, et une
attestation de coupure réseau au niveau OS. Hors de la fenêtre, ou si une seule condition manque, `Window.open` refuse.

Ce module ne contacte personne. `validate` retourne la LISTE des problèmes (vide = valide) pour que le propriétaire voie tout d'un coup.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import contract as c
from ..harness.corpus import PILOT_IDS
from ..providers import Prices, finite_nonneg

MAX_WINDOW = timedelta(hours=48)
MAX_PRICE_AGE = timedelta(days=30)
MAX_LOGICAL_CALLS = 20           # 10 cases x (1 rédaction + 1 critique)
HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
REQUIRED = ("campaign_id", "approved_by", "approved_at", "expires_at", "model", "provider_host", "endpoint_path", "currency", "ceiling_usd",
            "input_per_m", "output_per_m", "prices_as_of", "prices_source", "max_logical_calls", "strata", "topics", "max_input_tokens",
            "max_output_tokens", "tokenizer_id", "corpus_sha256", "baseline_rendered_sha256", "egress_attestation_sha256")


def _when(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None   # un instant sans fuseau est ambigu : refusé


@dataclass(frozen=True)
class CampaignAuthorization:
    raw: dict = field(repr=False)

    def __getattr__(self, name):
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    @property
    def prices(self) -> Prices:
        return Prices(self.raw["input_per_m"], self.raw["output_per_m"], self.raw["currency"], self.raw["prices_as_of"], self.raw["prices_source"])

    @property
    def digest(self) -> str:
        """Empreinte canonique de l'autorisation : consignée dans le journal, liée à l'attestation réseau."""
        return hashlib.sha256(json.dumps(self.raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate(raw, *, now: datetime | None = None, corpus_sha256: str | None = None, baseline_rendered_sha256: str | None = None) -> list[str]:
    """Liste de TOUS les problèmes. Une valeur absente, mal typée, non finie, périmée ou incohérente est un problème, jamais une valeur par défaut."""
    if not isinstance(raw, dict):
        return ["authorization must be a JSON object"]
    now = now or datetime.now(timezone.utc)
    problems = [f"missing field: {k}" for k in REQUIRED if raw.get(k) in (None, "", [])]
    if problems:
        return problems
    extra = set(raw) - set(REQUIRED)
    if extra:
        problems.append(f"unexpected fields: {sorted(extra)}")
    for key in ("campaign_id", "approved_by", "model", "tokenizer_id", "prices_source", "endpoint_path"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            problems.append(f"{key} must be a non-empty text")
    if "TODO" in json.dumps(raw).upper() or "PLACEHOLDER" in json.dumps(raw).upper():
        problems.append("the authorization still contains a TODO/PLACEHOLDER marker (it is the template)")
    approved, expires = _when(raw["approved_at"]), _when(raw["expires_at"])
    if approved is None or expires is None:
        problems.append("approved_at and expires_at must be ISO-8601 instants WITH a timezone")
    else:
        if not approved < expires <= approved + MAX_WINDOW:
            problems.append(f"the window must be positive and at most {MAX_WINDOW}")
        if not approved <= now < expires:
            problems.append("the authorization is not valid at this instant (outside its window)")
    if not isinstance(raw["provider_host"], str) or not HOST.match(raw["provider_host"]):
        problems.append("provider_host must be one lowercase fully qualified host name (no scheme, path, port, wildcard or IP literal)")
    if not isinstance(raw["endpoint_path"], str) or not raw["endpoint_path"].startswith("/") or ".." in raw["endpoint_path"] or "?" in raw["endpoint_path"]:
        problems.append("endpoint_path must be an absolute path without query or '..'")
    for key in ("ceiling_usd", "input_per_m", "output_per_m"):
        if not finite_nonneg(raw[key]):
            problems.append(f"{key} must be finite and non-negative")
    if finite_nonneg(raw["ceiling_usd"]) and raw["ceiling_usd"] <= 0:
        problems.append("ceiling_usd must be strictly positive")
    for key in ("max_logical_calls", "max_input_tokens", "max_output_tokens"):
        if not isinstance(raw[key], int) or isinstance(raw[key], bool) or raw[key] <= 0:
            problems.append(f"{key} must be a positive integer")
    if isinstance(raw["max_logical_calls"], int) and not isinstance(raw["max_logical_calls"], bool) and raw["max_logical_calls"] > MAX_LOGICAL_CALLS:
        problems.append(f"max_logical_calls cannot exceed {MAX_LOGICAL_CALLS} (10 cases x 2)")
    if raw["strata"] != ["standard"]:
        problems.append("strata must be exactly ['standard'] (Story Visual and Quiz are out of scope)")
    if not isinstance(raw["topics"], list) or sorted(raw["topics"]) != sorted(PILOT_IDS):
        problems.append(f"topics must be exactly the five pilot subjects {sorted(PILOT_IDS)}")
    as_of = _when(str(raw["prices_as_of"]) + ("T00:00:00+00:00" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw["prices_as_of"])) else ""))
    if as_of is None:
        problems.append("prices_as_of must be an ISO date")
    elif approved is not None and not timedelta(0) <= approved - as_of <= MAX_PRICE_AGE:
        problems.append(f"the price sheet must be dated at most {MAX_PRICE_AGE.days} days before the approval (and not in the future)")
    if isinstance(raw["prices_source"], str) and not raw["prices_source"].startswith("https://"):
        problems.append("prices_source must be the https URL of the official price page")
    for key, expected in (("corpus_sha256", corpus_sha256), ("baseline_rendered_sha256", baseline_rendered_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", str(raw[key])):
            problems.append(f"{key} must be a SHA-256")
        elif expected is not None and raw[key] != expected:
            problems.append(f"{key} does not match the frozen campaign inputs")
    if not re.fullmatch(r"[0-9a-f]{64}", str(raw["egress_attestation_sha256"])):
        problems.append("egress_attestation_sha256 must be the SHA-256 of the OS-level egress attestation")
    if not problems:  # le plafond doit pouvoir financer AU MOINS le premier appel au maximum
        first = (raw["max_input_tokens"] * raw["input_per_m"] + raw["max_output_tokens"] * raw["output_per_m"]) / 1e6
        if not math.isfinite(first) or first > raw["ceiling_usd"]:
            problems.append(f"ceiling_usd ({raw['ceiling_usd']}) cannot even fund one call at its maximum ({first:.6f})")
    return problems


def load(path: Path, **checks) -> CampaignAuthorization:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = validate(raw, **checks)
    if problems:
        raise c.ReviewError(c.BUDGET_EXHAUSTED, "invalid campaign authorization: " + "; ".join(problems))
    return CampaignAuthorization(raw)


class Window:
    """Fenêtre d'exécution : ouverte seulement avec une autorisation valide ET une attestation réseau reconnue ; refermée définitivement après usage."""

    def __init__(self):
        self._auth: CampaignAuthorization | None = None
        self._closed = False

    def open(self, auth: CampaignAuthorization, *, egress_attestation_sha256: str, now: datetime | None = None, **checks) -> None:
        if self._closed:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "a closed window cannot be reopened: a new authorization is required")
        problems = validate(auth.raw, now=now, **checks)
        if egress_attestation_sha256 != auth.raw["egress_attestation_sha256"]:
            problems.append("the OS-level egress attestation does not match the one the owner approved")
        if problems:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "window refused: " + "; ".join(problems))
        self._auth = auth

    def check(self, now: datetime | None = None) -> CampaignAuthorization:
        """À appeler AVANT chaque envoi : lève si la fenêtre n'est pas ouverte, est expirée ou a été fermée."""
        if self._closed or self._auth is None:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "no open authorization window: provider calls are forbidden")
        now = now or datetime.now(timezone.utc)
        if not _when(self._auth.raw["approved_at"]) <= now < _when(self._auth.raw["expires_at"]):
            self.close()
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "the authorization window has expired")
        return self._auth

    def close(self) -> None:
        self._closed, self._auth = True, None
