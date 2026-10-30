"""Fournisseur injectable, budget et coûts. Aucun fournisseur réel ici : le harness P0 reste hors réseau.

Règles : coût inconnu = `None` (jamais 0) ; estimation et facturation observée sont deux champs séparés ; la réservation
est ATOMIQUE (verrou) et refuse un appel dont le coût maximal n'est pas démontrable.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Callable

from . import contract as c


@dataclass(frozen=True)
class ProviderResult:
    text: str | None
    usage: dict | None = None          # {"input": int, "output": int} ou None si inconnu
    error: str | None = None
    latency_s: float | None = None
    http_attempts: int | None = 1      # déclaré par le fournisseur ; None = inconnu


Provider = Callable[[dict], ProviderResult]  # reçoit {"role", "prompt", "max_output_tokens", "timeout_s"}



def finite_nonneg(value) -> bool:
    """Vrai pour un nombre FINI et >= 0. Refuse NaN, +-inf, négatifs, booléens et tout non-nombre."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


@dataclass(frozen=True)
class Prices:
    input_per_m: float
    output_per_m: float
    currency: str = "USD"
    as_of: str = ""       # date de lecture du tarif officiel (obligatoire pour un appel réel)
    source: str = ""      # page de tarifs consultée

    def __post_init__(self):
        if not (finite_nonneg(self.input_per_m) and finite_nonneg(self.output_per_m)):
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "prices must be finite and non-negative")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "prices need a currency")


def _prices_ok(prices) -> bool:
    # Revalidé à CHAQUE calcul : un objet de tarifs construit sans passer par `Prices` (ou muté après coup) ne contourne rien.
    return prices is not None and finite_nonneg(getattr(prices, "input_per_m", None)) and finite_nonneg(getattr(prices, "output_per_m", None))


def estimate_usd(usage: dict | None, prices: Prices | None) -> float | None:
    """Coût ESTIMÉ (tokens x tarifs configurés), pas une facture. None si usage, tarif ou résultat invalide (jamais 0, jamais NaN)."""
    if not isinstance(usage, dict) or not _prices_ok(prices):
        return None
    if not (finite_nonneg(usage.get("input")) and finite_nonneg(usage.get("output"))):
        return None
    cost = (usage["input"] * prices.input_per_m + usage["output"] * prices.output_per_m) / 1_000_000
    return cost if finite_nonneg(cost) else None


def prompt_tokens_upper(text: str) -> int:
    """Majorant du nombre de jetons d'entrée : 1 jeton pour 2 caractères.

    shortcut: majorant raisonnable pour le français et l'anglais, pas démontré pour tous les modèles ; à remplacer par le
    tokenizer du modèle choisi avant tout appel réel. Un prompt au-dessus du plafond est refusé AVANT toute réservation.
    """
    return -(-len(text) // 2)


def max_call_usd(prices: Prices | None, input_cap: int, output_cap: int) -> float | None:
    """Coût maximal d'UN appel sous les plafonds de tokens. None (= pas d'appel) si tarif, plafond ou résultat n'est pas fini et >= 0."""
    if not _prices_ok(prices) or not (finite_nonneg(input_cap) and finite_nonneg(output_cap)):
        return None
    cost = (input_cap * prices.input_per_m + output_cap * prices.output_per_m) / 1_000_000
    return cost if finite_nonneg(cost) else None


@dataclass
class Budget:
    """Plafond monétaire global. `reserve` AVANT chaque tentative ; inconnu, invalide ou insuffisant = refus, aucun appel."""
    ceiling_usd: float
    reserved: dict = field(default_factory=dict)
    settled_usd: float = 0.0
    unknown_calls: int = 0
    overruns: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if not finite_nonneg(self.ceiling_usd):
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "the budget ceiling must be finite and non-negative")

    def committed(self) -> float:
        return self.settled_usd + sum(self.reserved.values())

    def reserve(self, label: str, max_usd: float | None) -> None:
        with self._lock:
            if not finite_nonneg(max_usd):  # None, NaN, +-inf, négatif : le coût maximal n'est pas démontrable
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: maximum cost is unknown or invalid, no call")
            if not finite_nonneg(self.ceiling_usd) or self.committed() + max_usd > self.ceiling_usd + 1e-12:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: {max_usd:.6f} USD would exceed the ceiling")
            self.reserved[label] = max_usd

    def settle(self, label: str, actual_estimate_usd: float | None) -> bool:
        """Remplace la réservation par l'estimation. Estimation inconnue OU invalide : on GARDE la réservation (prudence).

        Retourne True si l'estimation DÉPASSE la réservation (plafond de tokens non tenu) : le dépassement est enregistré, jamais masqué.
        """
        with self._lock:
            held = self.reserved.pop(label, 0.0)
            if not finite_nonneg(actual_estimate_usd):
                self.settled_usd += held
                self.unknown_calls += 1
                return False
            self.settled_usd += actual_estimate_usd
            if actual_estimate_usd > held + 1e-12:
                self.overruns += 1
                return True
            return False
