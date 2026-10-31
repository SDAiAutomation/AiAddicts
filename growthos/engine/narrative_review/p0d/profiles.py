"""Profil d'un MODÈLE autorisé à recevoir des appels, et validation stricte du corps de requête.

Le choix du modèle reste au propriétaire : AUCUN profil n'est enregistré ici. Un modèle sans profil (`ModelUnknown`) ne reçoit aucun appel. Le profil dit, pour CE modèle :
le nom du paramètre qui plafonne la sortie, la politique de raisonnement (unités facturables), les paramètres supplémentaires autorisés (liste explicite, chacun avec son
validateur) et l'identifiant du tokenizer. Le corps final est validé OCTET PAR OCTET juste avant l'envoi : une clé inconnue, un paramètre protégé, un type inattendu ou une
clé en double refuse l'envoi.
"""
from __future__ import annotations

import hashlib
import json
import math
from types import MappingProxyType
from dataclasses import dataclass, field
from typing import Callable, Mapping

from .. import contract as c

MAX_OUTPUT_PARAMS = ("max_tokens", "max_completion_tokens", "max_output_tokens")
REASONING_POLICIES = ("not_supported_by_model", "included_in_max_output", "separate_cap")
# Paramètres que la campagne contrôle ou qui peuvent multiplier les unités facturables : jamais acceptés comme « extras », même listés.
PROTECTED = frozenset({"model", "messages", "stream", "stream_options", "n", "best_of", "tools", "tool_choice", "functions", "function_call", "max_tokens",
                       "max_completion_tokens", "max_output_tokens", "max_tokens_to_sample", "prompt", "input", "instructions", "store", "background"})
REASONING_NAMES = frozenset({"reasoning", "reasoning_effort", "thinking", "budget_tokens", "max_reasoning_tokens", "thinking_budget"})
MAX_MESSAGE_CHARS = 200_000


class ModelUnknown(c.ReviewError):
    def __init__(self, model):
        super().__init__(c.BUDGET_EXHAUSTED, f"no profile registered for model {model!r}: no call")


@dataclass(frozen=True)
class BodyPolicy:
    model: str
    max_output_param: str
    reasoning_policy: str
    tokenizer_id: str
    allowed_extra: Mapping[str, Callable[[object], bool]] = field(default_factory=dict)
    reasoning_param: str | None = None       # requis si reasoning_policy == "separate_cap" : le paramètre qui porte le plafond de raisonnement. Sa valeur n'est JAMAIS fournie par
                                             # l'appelant : elle est construite depuis `reasoning_cap_tokens` de l'autorisation et validée comme égale à celle-ci.

    def __post_init__(self):
        object.__setattr__(self, "allowed_extra", MappingProxyType(dict(self.allowed_extra)))   # copie figée : modifier le dict d'origine ne change plus le profil

    def fingerprint(self) -> str:
        """Empreinte des paramètres du profil (les validateurs sont identifiés par leur nom qualifié) : détecte un profil remplacé ou altéré après l'ouverture de la fenêtre."""
        data = {"model": self.model, "max_output_param": self.max_output_param, "reasoning_policy": self.reasoning_policy, "tokenizer_id": self.tokenizer_id,
                "reasoning_param": self.reasoning_param, "allowed_extra": {k: getattr(v, "__qualname__", repr(v)) for k, v in sorted(self.allowed_extra.items())}}
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def problems(self) -> list[str]:
        out = []
        if not isinstance(self.model, str) or not self.model.strip():
            out.append("profile model must be a non-empty text")
        if self.max_output_param not in MAX_OUTPUT_PARAMS:
            out.append(f"max_output_param must be one of {MAX_OUTPUT_PARAMS}")
        if self.reasoning_policy not in REASONING_POLICIES:
            out.append(f"reasoning_policy must be one of {REASONING_POLICIES}")
        if not isinstance(self.tokenizer_id, str) or not self.tokenizer_id:
            out.append("tokenizer_id is required")
        for name, validator in self.allowed_extra.items():
            if not isinstance(name, str) or name in PROTECTED or not callable(validator):
                out.append(f"extra parameter {name!r} is protected or has no validator")
            if name in REASONING_NAMES or name == self.reasoning_param:
                out.append(f"reasoning parameter {name!r} can never be a caller-supplied extra: it is built from the approved reasoning_cap_tokens")
        if self.reasoning_policy == "separate_cap" and (not isinstance(self.reasoning_param, str) or self.reasoning_param not in REASONING_NAMES):
            out.append(f"separate_cap needs reasoning_param, one of {sorted(REASONING_NAMES)}")
        if self.reasoning_policy != "separate_cap" and self.reasoning_param:
            out.append("reasoning_param is only meaningful with 'separate_cap'")
        return out


_profiles: dict[str, BodyPolicy] = {}


def register_profile(profile: BodyPolicy) -> None:
    problems = profile.problems()
    if problems:
        raise c.ReviewError(c.BUDGET_EXHAUSTED, "invalid model profile: " + "; ".join(problems))
    _profiles[profile.model] = profile


def profile_for(model) -> BodyPolicy:
    if not isinstance(model, str) or model not in _profiles:
        raise ModelUnknown(model)
    return _profiles[model]


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key in the request body")
    return dict(pairs)


def _reject_constant(name):
    raise ValueError(f"non-finite constant {name} in the request body")


def validate_body(raw: bytes, *, model: str, max_output_tokens: int, profile: BodyPolicy, reasoning_cap_tokens: int | None = None) -> dict:
    """Valide le corps EXACT qui va partir. Retourne le corps analysé ou lève `ReviewError` : le transport n'envoie rien en cas d'erreur."""
    def bad(msg):
        raise c.ReviewError(c.INVALID_RESPONSE, f"request body refused: {msg}")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        bad(f"not valid strict JSON ({type(exc).__name__}: {exc})")
    if not isinstance(body, dict):
        bad("the body must be a JSON object")
    separate = profile.reasoning_policy == "separate_cap"
    fixed = {"model", "messages", profile.max_output_param} | ({profile.reasoning_param} if separate else set())
    unknown = set(body) - fixed - set(profile.allowed_extra)
    if unknown:
        bad(f"unexpected parameters {sorted(unknown)} (explicit allowlist)")
    missing = fixed - set(body)
    if missing:
        bad(f"missing parameters {sorted(missing)}")
    if body["model"] != model or body["model"] != profile.model:
        bad("model differs from the authorised model")
    messages = body["messages"]
    if not isinstance(messages, list) or len(messages) != 2:
        bad("messages must be exactly one system and one user message")
    for message, role in zip(messages, ("system", "user")):
        if not (isinstance(message, dict) and set(message) == {"role", "content"} and message["role"] == role and isinstance(message["content"], str)
                and 0 < len(message["content"]) <= MAX_MESSAGE_CHARS):
            bad(f"the {role} message is malformed")
    cap = body[profile.max_output_param]
    if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= max_output_tokens:
        bad(f"{profile.max_output_param} must be an integer within 1..{max_output_tokens}")
    for name, value in body.items():
        if name in fixed:
            continue
        validator = profile.allowed_extra[name]
        try:
            ok = validator(value) is True
        except Exception:  # noqa: BLE001 - un validateur qui échoue refuse le paramètre
            ok = False
        if not ok or (isinstance(value, float) and not math.isfinite(value)):
            bad(f"parameter {name!r} failed its validator")
    if separate:   # plafond de raisonnement : EXACTEMENT celui de l'autorisation (ni plus, ni moins), sinon rien ne part
        value = body[profile.reasoning_param]
        if not (isinstance(reasoning_cap_tokens, int) and not isinstance(reasoning_cap_tokens, bool) and reasoning_cap_tokens > 0):
            bad("the authorization has no valid reasoning cap to compare with")
        if not isinstance(value, int) or isinstance(value, bool) or value != reasoning_cap_tokens:
            bad(f"{profile.reasoning_param} must equal the approved reasoning cap ({reasoning_cap_tokens})")
    return body
