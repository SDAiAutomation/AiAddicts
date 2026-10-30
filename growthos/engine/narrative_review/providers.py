"""Fournisseur injectable, budget et coûts. Aucun fournisseur réel ici : le harness P0 reste hors réseau.

Règles : coût inconnu = `None` (jamais 0) ; estimation et facturation observée sont deux champs séparés ; la réservation
est ATOMIQUE (verrou) et refuse un appel dont le coût maximal n'est pas démontrable.
"""
from __future__ import annotations

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


@dataclass(frozen=True)
class Prices:
    input_per_m: float
    output_per_m: float
    currency: str = "USD"
    as_of: str = ""       # date de lecture du tarif officiel (obligatoire pour un appel réel)
    source: str = ""      # page de tarifs consultée


def estimate_usd(usage: dict | None, prices: Prices | None) -> float | None:
    """Coût ESTIMÉ (tokens x tarifs configurés), pas une facture. None si usage ou tarif inconnu."""
    if not usage or prices is None or usage.get("input") is None or usage.get("output") is None:
        return None
    return (usage["input"] * prices.input_per_m + usage["output"] * prices.output_per_m) / 1_000_000


def max_call_usd(prices: Prices | None, input_cap: int, output_cap: int) -> float | None:
    """Coût maximal d'UN appel sous les plafonds de tokens. None (= pas d'appel) si le tarif est inconnu."""
    return None if prices is None else (input_cap * prices.input_per_m + output_cap * prices.output_per_m) / 1_000_000


@dataclass
class Budget:
    """Plafond monétaire global. `reserve` AVANT chaque tentative ; inconnu ou insuffisant = refus, aucun appel."""
    ceiling_usd: float
    reserved: dict = field(default_factory=dict)
    settled_usd: float = 0.0
    unknown_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def committed(self) -> float:
        return self.settled_usd + sum(self.reserved.values())

    def reserve(self, label: str, max_usd: float | None) -> None:
        with self._lock:
            if max_usd is None or max_usd < 0:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: maximum cost is unknown, no call")
            if self.committed() + max_usd > self.ceiling_usd + 1e-12:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: {max_usd:.6f} USD would exceed the ceiling")
            self.reserved[label] = max_usd

    def settle(self, label: str, actual_estimate_usd: float | None) -> None:
        """Remplace la réservation par l'estimation. Estimation inconnue : on GARDE la réservation (prudence)."""
        with self._lock:
            held = self.reserved.pop(label, 0.0)
            if actual_estimate_usd is None:
                self.settled_usd += held
                self.unknown_calls += 1
            else:
                self.settled_usd += actual_estimate_usd
