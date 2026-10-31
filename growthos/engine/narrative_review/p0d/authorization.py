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
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable

from .. import contract as c
from ..harness.corpus import PILOT_IDS
from ..providers import Prices, finite_nonneg
from ..reviewer import MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS
from ..providers import max_call_usd as _max_call_usd
from .profiles import REASONING_POLICIES, ModelUnknown, profile_for
from .egress import Attestation, EgressController
from .tokenizer import ValidationRecord, factory_for, identity, require_validated

MAX_WINDOW = timedelta(hours=48)
MAX_PRICE_AGE = timedelta(days=30)
MAX_LOGICAL_CALLS = 20           # 10 cases x (1 rédaction + 1 critique)
HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
REQUIRED = ("campaign_id", "approved_by", "approved_at", "expires_at", "model", "provider_host", "endpoint_path", "currency", "ceiling_usd",
            "input_per_m", "output_per_m", "prices_as_of", "prices_source", "max_logical_calls", "strata", "topics", "max_input_tokens",
            "max_output_tokens", "tokenizer_id", "tokenizer_validation_sha256", "reasoning_policy", "corpus_sha256", "baseline_rendered_sha256",
            "egress_attestation_sha256")
SEPARATE_CAP_FIELDS = ("reasoning_cap_tokens", "reasoning_per_m")     # exigés si `reasoning_policy` == "separate_cap" (unité facturable distincte)


def _when(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None   # un instant sans fuseau est ambigu : refusé


def _freeze(value):
    """Copie profonde IMMUABLE : dict -> MappingProxyType, list -> tuple. Rien de ce que renvoie l'autorisation ne peut être modifié en place."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value):
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class CampaignAuthorization:
    """Paramètres APPROUVÉS, figés à la construction : copie profonde immuable (modifier le dictionnaire d'origine ne change rien, `auth.raw[...] = x` lève une erreur)."""
    raw: Mapping = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, "raw", _freeze(self.raw))

    def __getattr__(self, name):
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    @property
    def prices(self) -> Prices:
        return Prices(self.raw["input_per_m"], self.raw["output_per_m"], self.raw["currency"], self.raw["prices_as_of"], self.raw["prices_source"],
                      *_reasoning_unit(self.raw))

    @property
    def digest(self) -> str:
        """Empreinte canonique de l'autorisation : consignée dans le journal, liée à l'attestation réseau."""
        return hashlib.sha256(json.dumps(_thaw(self.raw), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate(raw, *, now: datetime | None = None, corpus_sha256: str | None = None, baseline_rendered_sha256: str | None = None) -> list[str]:
    """Liste de TOUS les problèmes. Une valeur absente, mal typée, non finie, périmée ou incohérente est un problème, jamais une valeur par défaut."""
    raw = _thaw(raw) if isinstance(raw, Mapping) else raw
    if not isinstance(raw, dict):
        return ["authorization must be a JSON object"]
    now = now or datetime.now(timezone.utc)
    problems = [f"missing field: {k}" for k in REQUIRED if raw.get(k) in (None, "", [])]
    if problems:
        return problems
    if raw["reasoning_policy"] not in REASONING_POLICIES:
        problems.append(f"reasoning_policy must be one of {REASONING_POLICIES}: unbounded billable units mean no call")
    separate = raw["reasoning_policy"] == "separate_cap"
    for key in SEPARATE_CAP_FIELDS:   # tarifs et plafonds COMPLETS : une unité facturable sans plafond ou sans prix = aucun appel
        if separate and raw.get(key) in (None, "", []):
            problems.append(f"missing field: {key} (required by reasoning_policy 'separate_cap')")
        elif not separate and key in raw:
            problems.append(f"{key} is only allowed with reasoning_policy 'separate_cap'")
    if separate:
        if not finite_nonneg(raw.get("reasoning_per_m")):
            problems.append("reasoning_per_m must be finite and non-negative")
        if not isinstance(raw.get("reasoning_cap_tokens"), int) or isinstance(raw.get("reasoning_cap_tokens"), bool) or raw.get("reasoning_cap_tokens", 0) <= 0:
            problems.append("reasoning_cap_tokens must be a positive integer")
    extra = set(raw) - set(REQUIRED) - set(SEPARATE_CAP_FIELDS)
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
    for key, harness_limit in (("max_input_tokens", MAX_INPUT_TOKENS), ("max_output_tokens", MAX_OUTPUT_TOKENS)):
        if raw[key] != harness_limit:   # la réservation du harness et du critique utilise ces constantes : l'autorisation ne peut pas en annoncer d'autres
            problems.append(f"{key} must equal the harness limit {harness_limit}: one reservation formula for authorization, harness and critic")
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
    for key in ("egress_attestation_sha256", "tokenizer_validation_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(raw[key])):
            problems.append(f"{key} must be a SHA-256 ({'the OS-level egress attestation' if key.startswith('egress') else 'the approved tokenizer validation record'})")
    if not problems:  # le plafond doit pouvoir financer AU MOINS le premier appel au maximum (entrée + sortie + unité de raisonnement distincte éventuelle)
        first = max_call_usd(raw)
        if first is None or first > raw["ceiling_usd"]:
            problems.append(f"ceiling_usd ({raw['ceiling_usd']}) cannot even fund one call at its maximum ({first})")
    return problems


def max_call_usd(raw: dict) -> float | None:
    """Coût maximal d'UN appel sous TOUS les plafonds facturables de l'autorisation (entrée, sortie, et raisonnement s'il est une unité distincte). None si incomplet."""
    try:
        return _max_call_usd(Prices(raw["input_per_m"], raw["output_per_m"], raw["currency"], raw["prices_as_of"], raw["prices_source"],
                                    *_reasoning_unit(raw)), raw["max_input_tokens"], raw["max_output_tokens"])
    except (KeyError, TypeError, c.ReviewError):
        return None


def _reasoning_unit(raw: dict) -> tuple:
    """(prix, plafond) de l'unité de raisonnement distincte, ou (None, None) : un seul endroit pour le dire, partagé par `prices` et `max_call_usd`."""
    return (raw.get("reasoning_per_m"), raw.get("reasoning_cap_tokens")) if raw.get("reasoning_policy") == "separate_cap" else (None, None)


def load(path: Path, **checks) -> CampaignAuthorization:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = validate(raw, **checks)
    if problems:
        raise c.ReviewError(c.BUDGET_EXHAUSTED, "invalid campaign authorization: " + "; ".join(problems))
    return CampaignAuthorization(raw)


class Window:
    """Fenêtre d'exécution : ouverte seulement avec une autorisation valide, un état réseau VIVANT vérifié, un modèle connu et un tokenizer validé ; refermée définitivement après usage.

    À l'ouverture sont FIGÉS : l'autorisation (copie immuable + empreinte), le profil du modèle (objet + empreinte), les tarifs, l'attestation réseau approuvée, l'enregistrement de
    validation du tokenizer, ET l'implémentation du tokenizer effectivement résolue (instance + fabrique du registre + empreinte d'identité).
    Chaque vérification ci-dessous les REconfronte à l'état vivant ; la moindre différence ou incertitude ferme la fenêtre définitivement et refuse l'appel.
    Un contrôleur réseau (`EgressController`) est OBLIGATOIRE : absence, erreur, attestation incohérente ou état inconnu = refus. L'horloge est injectable pour les tests."""

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._auth: CampaignAuthorization | None = None
        self._closed = False
        self._frozen: dict | None = None
        self._controller: EgressController | None = None
        self._egress_kind = "none"
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # --- ouverture -----------------------------------------------------------------------------------------------------------------------------

    def open(self, auth: CampaignAuthorization, *, egress_attestation_sha256: str, tokenizer_validation: ValidationRecord | None, egress_controller: EgressController | None,
             now: datetime | None = None, **checks) -> None:
        """Ouvre la fenêtre seulement si TOUT est établi : autorisation valide à l'instant EFFECTIF, état réseau vivant « rest » attesté et conforme à l'attestation approuvée, modèle
        CONNU (profil cohérent), tokenizer résolu ET validé POUR CETTE IMPLÉMENTATION. Sinon : aucune ouverture, aucun appel."""
        if self._closed or self._auth is not None:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "a closed or already open window cannot be (re)opened: a new authorization is required")
        now = now or self._clock()
        problems = validate(auth.raw, now=now, **checks)   # une autorisation déjà expirée à l'instant effectif de l'ouverture est refusée
        if egress_attestation_sha256 != auth.raw["egress_attestation_sha256"]:
            problems.append("the OS-level egress attestation does not match the one the owner approved")
        if egress_controller is None or not callable(getattr(egress_controller, "check", None)):
            problems.append("a live egress controller is mandatory: without a live network check there is no window")
        profile = counter = factory = plan_sha = None
        if not problems:
            try:
                profile = profile_for(auth.raw["model"])
                if (profile.reasoning_policy, profile.tokenizer_id) != (auth.raw["reasoning_policy"], auth.raw["tokenizer_id"]):
                    problems.append("the model profile (reasoning policy, tokenizer) differs from the authorization")
                factory = factory_for(auth.raw["tokenizer_id"])
                counter = factory()
                require_validated(tokenizer_validation, model=auth.raw["model"], tokenizer_id=auth.raw["tokenizer_id"],
                                  expected_sha256=auth.raw["tokenizer_validation_sha256"], counter=counter)
                attestation = self._live(egress_controller, "rest")   # AVANT toute ouverture : le courtier doit être à l'état de repos attesté, verrou présent
                if attestation.sha256 != auth.raw["egress_attestation_sha256"]:
                    problems.append("the live network state is not the attested rest state the owner approved")
                plan_sha = attestation.plan_sha256
            except c.ReviewError as exc:   # ModelUnknown, TokenizerRequired, TokenizerNotValidated, contrôle réseau
                problems.append(exc.message)
        if problems:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "window refused: " + "; ".join(problems))
        self._frozen = {"auth": auth, "digest": auth.digest, "profile": profile, "profile_fp": profile.fingerprint(), "prices": auth.prices,
                        "egress": egress_attestation_sha256, "tokenizer_record": tokenizer_validation.sha256, "tokenizer_id": auth.raw["tokenizer_id"],
                        "factory": factory, "counter": counter, "counter_identity": identity(counter), "counter_type": type(counter), "plan_sha": plan_sha}
        self._controller, self._egress_kind = egress_controller, getattr(egress_controller, "kind", "unknown")
        self._auth = auth

    @staticmethod
    def _live(controller, expect: str) -> Attestation:
        """Appelle le contrôleur et refuse tout ce qui n'est pas une attestation positive, du bon état attendu : erreur, réponse d'un autre type, problèmes, état inconnu."""
        try:
            attestation = controller.check(expect)
        except Exception as exc:  # noqa: BLE001 - une erreur de contrôle est un refus
            raise c.ReviewError(c.BUDGET_EXHAUSTED, f"the live network check failed ({type(exc).__name__}): refused") from exc
        if not isinstance(attestation, Attestation) or attestation.ok is not True or attestation.problems or attestation.expected_state != expect:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, f"the live network state is not the attested '{expect}' state: refused")
        return attestation

    @property
    def egress_kind(self) -> str:
        """"os_readonly" ou "simulated" : ce que vaut le contrôle réseau. "simulated" n'est JAMAIS une preuve de coupure au niveau du système d'exploitation."""
        return self._egress_kind

    @property
    def closed(self) -> bool:
        return self._closed

    # --- vérifications (chacune ferme la fenêtre si elle échoue) --------------------------------------------------------------------------------

    def _fail(self, message: str):
        self.close()
        raise c.ReviewError(c.BUDGET_EXHAUSTED, "window closed: " + message)

    def _need_open(self) -> dict:
        if self._closed or self._auth is None:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "no open authorization window: provider calls are forbidden")
        return self._frozen

    def check_time(self, now: datetime | None = None) -> CampaignAuthorization:
        self._need_open()
        now = now or self._clock()
        if not _when(self._auth.raw["approved_at"]) <= now < _when(self._auth.raw["expires_at"]):
            self.close()
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "the authorization window has expired")
        return self._auth

    def verify_fingerprints(self) -> None:
        """Autorisation, tarifs, attestation approuvée, enregistrement du tokenizer et PROFIL du modèle : identiques à ce qui a été approuvé à l'ouverture."""
        f = self._need_open()
        try:
            auth = self._auth
            if auth is not f["auth"] or auth.digest != f["digest"]:
                return self._fail("the authorization changed after the window was opened")
            if auth.prices != f["prices"]:
                return self._fail("the price sheet changed after the window was opened")
            if auth.raw["egress_attestation_sha256"] != f["egress"]:
                return self._fail("the egress attestation changed after the window was opened")
            if auth.raw["tokenizer_validation_sha256"] != f["tokenizer_record"]:
                return self._fail("the tokenizer validation changed after the window was opened")
            live = profile_for(auth.raw["model"])
            if live is not f["profile"] or live.fingerprint() != f["profile_fp"]:
                return self._fail("the model profile was replaced or altered after the window was opened")
        except c.ReviewError:
            raise
        except Exception as exc:  # noqa: BLE001 - l'incertitude ferme la fenêtre
            self._fail(f"integrity could not be established ({type(exc).__name__})")

    def verify_tokenizer(self) -> None:
        """L'implémentation du tokenizer résolue à l'ouverture est toujours celle du registre, et n'a pas changé (classe, état d'instance, code de `count`)."""
        f = self._need_open()
        try:
            if factory_for(f["tokenizer_id"]) is not f["factory"]:
                return self._fail("the tokenizer factory was replaced in the registry after the window was opened")
            counter = f["counter"]
            if type(counter) is not f["counter_type"] or identity(counter) != f["counter_identity"]:
                return self._fail("the pinned token counter was altered after the window was opened")
        except c.ReviewError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._fail(f"tokenizer identity could not be established ({type(exc).__name__})")

    def verify_network(self) -> None:
        """État réseau VIVANT « open » attesté, lié au même plan que celui vu à l'ouverture. Contrôleur absent, erreur, attestation incohérente ou inconnue = fenêtre fermée."""
        f = self._need_open()
        try:
            if self._controller is None:
                return self._fail("no live egress controller")
            attestation = self._live(self._controller, "open")
            if not f["plan_sha"] or attestation.plan_sha256 != f["plan_sha"]:
                return self._fail("the live network attestation is bound to another plan than the one seen at opening")
        except c.ReviewError as exc:
            if self._closed:
                raise
            self._fail(exc.message)

    def pinned_counter(self):
        """Le compteur de jetons FIGÉ à l'ouverture (jamais une nouvelle résolution du registre)."""
        return self._need_open()["counter"]

    def pinned_profile(self):
        return self._need_open()["profile"]

    def check(self, now: datetime | None = None) -> CampaignAuthorization:
        """À appeler AVANT chaque réservation et chaque envoi : temps, empreintes, tokenizer et état réseau vivant. Lève (et ferme) au moindre écart."""
        self.check_time(now)
        self.verify_fingerprints()
        self.verify_tokenizer()
        self.verify_network()
        return self._auth

    def close(self) -> None:
        self._closed, self._auth, self._frozen, self._controller = True, None, None, None
