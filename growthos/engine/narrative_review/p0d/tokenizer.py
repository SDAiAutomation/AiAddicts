"""Comptage de jetons d'entrée AVANT envoi. Le tokenizer exact dépend du MODÈLE CHOISI, qui ne l'est pas encore : ce module fournit l'interface, un majorant
conservateur sans dépendance, et le garde-fou « tokenizer inconnu = pas d'appel ».

- `char-upper-bound` : 1 jeton pour 2 caractères. Majorant raisonnable pour le français et l'anglais, PAS exact et PAS démontré pour tous les modèles ni pour les
  textes non latins. Il surestime volontairement ; il ne sous-estime pas pour un texte courant mais ce n'est pas prouvé, d'où le contrôle de calibration ci-dessous.
- Un tokenizer propre à un modèle (par ex. une table BPE) doit être ENREGISTRÉ par le propriétaire avec `register`. Un identifiant d'autorisation sans compteur enregistré
  lève `TokenizerRequired` : aucun repli silencieux. Aucun tokenizer réseau n'est téléchargé ici (aucune dépendance, aucun accès réseau).
- Calibration : après chaque réponse, les jetons d'entrée RENVOYÉS par le fournisseur sont comparés au majorant compté. S'ils le dépassent, le compteur sous-estime :
  le transport se déclenche et plus aucun appel n'est envoyé.
"""
from __future__ import annotations

import math
from typing import Callable, Protocol

from .. import contract as c

CHAR_BOUND_ID = "char-upper-bound"
CHAT_OVERHEAD_TOKENS = 16   # enveloppe de messages (rôles, séparateurs) : marge forfaitaire, à calibrer sur le modèle choisi


class TokenCounter(Protocol):
    id: str
    exact: bool

    def count(self, text: str) -> int: ...


class CharUpperBound:
    id, exact = CHAR_BOUND_ID, False

    def count(self, text: str) -> int:
        return -(-len(text) // 2)


class TokenizerRequired(c.ReviewError):
    def __init__(self, tokenizer_id: str):
        super().__init__(c.BUDGET_EXHAUSTED, f"no token counter registered for {tokenizer_id!r}: register the chosen model's tokenizer or use {CHAR_BOUND_ID!r} (not exact)")


_registry: dict[str, Callable[[], TokenCounter]] = {CHAR_BOUND_ID: CharUpperBound}


def register(counter_factory: Callable[[], TokenCounter]) -> None:
    counter = counter_factory()
    if not isinstance(counter.id, str) or not counter.id or counter.id == CHAR_BOUND_ID and not isinstance(counter, CharUpperBound):
        raise ValueError("a token counter needs its own non-empty id")
    _registry[counter.id] = counter_factory


def resolve(tokenizer_id: str) -> TokenCounter:
    try:
        return _registry[tokenizer_id]()
    except KeyError as exc:
        raise TokenizerRequired(tokenizer_id) from exc


def upper_input_tokens(counter: TokenCounter, system: str, user: str, *, safety: float = 1.10) -> int:
    """Majorant des jetons d'entrée d'un appel de chat : mesure du compteur x marge, jamais inférieur au majorant par caractères."""
    if not (math.isfinite(safety) and safety >= 1.0):
        raise ValueError("safety must be finite and >= 1")
    measured = math.ceil((counter.count(system) + counter.count(user) + CHAT_OVERHEAD_TOKENS) * safety)
    floor = CharUpperBound().count(system) + CharUpperBound().count(user) if not counter.exact else 0
    return max(measured, floor)


def underestimated(counted_upper: int, reported_input_tokens: int | None) -> bool:
    """Vrai si le fournisseur a facturé PLUS d'entrée que le majorant compté (le compteur sous-estime). Inconnu (None) n'est pas « correct » : à traiter à part."""
    return reported_input_tokens is not None and reported_input_tokens > counted_upper
