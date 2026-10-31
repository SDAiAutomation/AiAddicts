"""Comptage de jetons d'entrée AVANT envoi : une ESTIMATION, jamais un majorant garanti.

Le tokenizer exact dépend du MODÈLE CHOISI par le propriétaire, qui ne l'est pas encore. Ce module fournit :
- l'interface `TokenCounter` et l'heuristique `char-heuristic-2cpt` (1 jeton pour 2 caractères, NON exacte, NON démontrée, NON validée) ;
- `register()` pour le tokenizer du modèle ; un identifiant sans compteur enregistré lève `TokenizerRequired` (aucun repli silencieux) ;
- la VALIDATION : un compteur n'est admis pour un appel réel que s'il a été validé sur des échantillons de consommation RÉELLE renvoyée par le fournisseur
  (`validate_counter` -> `ValidationRecord`, produit lors d'une calibration séparée et autorisée) et si l'empreinte de cet enregistrement figure dans l'autorisation.
  Sans enregistrement valide : aucun appel.
Même validé, un compteur reste une estimation : la consommation réelle n'est connue que dans la réponse. Un dépassement de la réservation ou du compteur arrête la campagne.
Aucun tokenizer n'est téléchargé (aucune dépendance, aucun accès réseau).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Callable, Protocol

from .. import contract as c

HEURISTIC_ID = "char-heuristic-2cpt"
CHAT_OVERHEAD_TOKENS = 16   # enveloppe de messages (rôles, séparateurs) : marge forfaitaire, à calibrer sur le modèle choisi
MIN_VALIDATION_SAMPLES = 20


class TokenCounter(Protocol):
    id: str
    exact: bool

    def count(self, text: str) -> int: ...


class CharHeuristic:
    """ESTIMATION : 1 jeton pour 2 caractères. Ce n'est pas un majorant : elle peut sous-estimer (texte non latin, code, nombres, emoji)."""
    id, exact = HEURISTIC_ID, False

    def count(self, text: str) -> int:
        return -(-len(text) // 2)


class TokenizerRequired(c.ReviewError):
    def __init__(self, tokenizer_id: str):
        super().__init__(c.BUDGET_EXHAUSTED, f"no token counter registered for {tokenizer_id!r}: register the chosen model's tokenizer; the heuristic {HEURISTIC_ID!r} is an estimate and must be validated")


class TokenizerNotValidated(c.ReviewError):
    def __init__(self, why: str):
        super().__init__(c.BUDGET_EXHAUSTED, f"tokenizer not validated for this model: {why}; no call")


_registry: dict[str, Callable[[], TokenCounter]] = {HEURISTIC_ID: CharHeuristic}


def register(counter_factory: Callable[[], TokenCounter]) -> None:
    counter = counter_factory()
    if not isinstance(counter.id, str) or not counter.id or (counter.id == HEURISTIC_ID and not isinstance(counter, CharHeuristic)):
        raise ValueError("a token counter needs its own non-empty id")
    _registry[counter.id] = counter_factory


def resolve(tokenizer_id: str) -> TokenCounter:
    try:
        return _registry[tokenizer_id]()
    except KeyError as exc:
        raise TokenizerRequired(tokenizer_id) from exc


def estimate_input_tokens(counter: TokenCounter, system: str, user: str, *, safety: float = 1.10) -> int:
    """ESTIMATION des jetons d'entrée d'un appel de chat : mesure du compteur + enveloppe, x marge ; jamais inférieure à l'heuristique par caractères pour un compteur non exact."""
    if not (math.isfinite(safety) and safety >= 1.0):
        raise ValueError("safety must be finite and >= 1")
    measured = math.ceil((counter.count(system) + counter.count(user) + CHAT_OVERHEAD_TOKENS) * safety)
    floor = CharHeuristic().count(system) + CharHeuristic().count(user) if not counter.exact else 0
    return max(measured, floor)


def underestimated(estimate: int, reported_input_tokens: int | None) -> bool:
    """Vrai si le fournisseur a facturé PLUS d'entrée que l'estimation. Inconnu (None) n'est pas « correct » : à traiter à part (usage inconnu = arrêt)."""
    return reported_input_tokens is not None and reported_input_tokens > estimate


@dataclass(frozen=True)
class ValidationRecord:
    tokenizer_id: str
    model: str
    samples: int
    max_reported_over_estimate: float     # <= 1 : sur tous les échantillons, l'estimation couvrait la consommation réelle
    safety: float
    ok: bool
    sha256: str


def validate_counter(counter: TokenCounter, model: str, samples: list[tuple[str, str, int]], *, safety: float = 1.10) -> ValidationRecord:
    """Compare l'estimation du compteur à la consommation RÉELLE d'entrée renvoyée par le fournisseur pour `samples` = [(système, utilisateur, jetons d'entrée facturés)].

    Fonction pure : elle ne fait aucun appel. Les échantillons viennent d'une calibration séparée et autorisée (non faite). `ok` exige au moins
    `MIN_VALIDATION_SAMPLES` échantillons, tous valides, et que l'estimation couvre la consommation réelle sur CHACUN d'eux."""
    worst, valid = 0.0, True
    for system, user, reported in samples:
        if not (isinstance(reported, int) and not isinstance(reported, bool) and reported > 0 and isinstance(system, str) and isinstance(user, str)):
            valid = False
            continue
        worst = max(worst, reported / estimate_input_tokens(counter, system, user, safety=safety))
    ok = valid and len(samples) >= MIN_VALIDATION_SAMPLES and worst <= 1.0
    canonical = json.dumps({"tokenizer_id": counter.id, "model": model, "samples": len(samples), "worst": round(worst, 9), "safety": safety, "ok": ok},
                           sort_keys=True, separators=(",", ":"))
    return ValidationRecord(counter.id, model, len(samples), worst, safety, ok, hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def require_validated(record: ValidationRecord | None, *, model: str, tokenizer_id: str, expected_sha256: str) -> None:
    """Refus (aucun appel) sans enregistrement de validation valide, du bon modèle et du bon tokenizer, dont l'empreinte est celle approuvée dans l'autorisation."""
    if record is None:
        raise TokenizerNotValidated("no validation record was provided")
    if not record.ok:
        raise TokenizerNotValidated(f"the validation record is not ok ({record.samples} samples, worst reported/estimate ratio {record.max_reported_over_estimate:.3f})")
    if (record.model, record.tokenizer_id) != (model, tokenizer_id):
        raise TokenizerNotValidated("the validation record is for another model or tokenizer")
    if record.sha256 != expected_sha256:
        raise TokenizerNotValidated("the validation record is not the one approved in the authorization")
