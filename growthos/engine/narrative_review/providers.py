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
    http_attempts: int | None = 1      # déclaré par le fournisseur ; None = inconnu (le transport instrumenté le MESURE : p0d/transport.py)
    observed_cost_usd: float | None = None   # coût RENVOYÉ par le fournisseur (jamais calculé ici) ; None = non fourni
    partial: bool = False                    # réponse tronquée ou filtrée (finish_reason != "stop") : le coût et le contenu ne sont pas fiables


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
    reasoning_per_m: float | None = None   # unité facturable distincte (politique de raisonnement `separate_cap`) ; None = non applicable
    reasoning_cap_tokens: int | None = None   # plafond de cette unité : prix ET plafond vont ensemble, l'un sans l'autre = aucun appel

    def __post_init__(self):
        if not (finite_nonneg(self.input_per_m) and finite_nonneg(self.output_per_m)):
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "prices must be finite and non-negative")
        if self.reasoning_per_m is not None and not finite_nonneg(self.reasoning_per_m):
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "reasoning_per_m must be finite and non-negative when given")
        cap = self.reasoning_cap_tokens
        if (self.reasoning_per_m is None) != (cap is None) or (cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0)):
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "reasoning_per_m and a positive integer reasoning_cap_tokens go together: a billable unit without a price or a cap means no call")
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
    total = usage["input"] * prices.input_per_m + usage["output"] * prices.output_per_m
    reasoning_price = getattr(prices, "reasoning_per_m", None)
    if "reasoning" in usage or reasoning_price is not None:   # unité facturable distincte : sans tarif ou sans valeur valide (ou valeur absente), le coût n'est PAS établi (jamais 0)
        if not (finite_nonneg(usage.get("reasoning")) and finite_nonneg(reasoning_price)):
            return None
        total += usage["reasoning"] * reasoning_price
    cost = total / 1_000_000
    return cost if finite_nonneg(cost) else None


def prompt_tokens_estimate(text: str) -> int:
    """ESTIMATION heuristique du nombre de jetons d'entrée : 1 jeton pour 2 caractères. Ce n'est PAS un majorant garanti.

    Elle sert de garde grossière dans le harness hors ligne. Pour un appel réel, seul un tokenizer VALIDÉ pour le modèle choisi (p0d/tokenizer.py) est admis ;
    même alors, la vraie consommation n'est connue que dans la réponse du fournisseur, et un dépassement de la réservation arrête la campagne.
    """
    return -(-len(text) // 2)


def max_call_usd(prices: Prices | None, input_cap: int, output_cap: int) -> float | None:
    """Coût maximal d'UN appel : l'UNIQUE calcul de réservation (autorisation, harness, critique, futur exécuteur). Couvre entrée, sortie et, si les tarifs le déclarent, l'unité de
    raisonnement distincte à son plafond. None (= pas d'appel) si un tarif, un plafond ou le résultat n'est pas fini et >= 0, ou si une unité a un prix sans plafond (ou l'inverse)."""
    if not _prices_ok(prices) or not (finite_nonneg(input_cap) and finite_nonneg(output_cap)):
        return None
    price, cap = getattr(prices, "reasoning_per_m", None), getattr(prices, "reasoning_cap_tokens", None)
    if (price is None) != (cap is None):
        return None
    cost = (input_cap * prices.input_per_m + output_cap * prices.output_per_m) / 1_000_000
    if price is not None:
        if not (finite_nonneg(price) and finite_nonneg(cap)):
            return None
        cost += cap * price / 1_000_000
    return cost if finite_nonneg(cost) else None


class Budget:
    """Plafond monétaire global. `reserve` AVANT chaque tentative ; inconnu, invalide ou insuffisant = refus, aucun appel.

    L'état comptable est ENCAPSULÉ (`__slots__`, propriétés en lecture seule, `reserved` rendu en copie) ET revalidé en entier, sous verrou,
    avant CHAQUE opération : plafond, montant consommé, chaque réservation et compteurs doivent être finis, positifs ou nuls et cohérents.
    Un état corrompu (y compris par contournement `object.__setattr__`) refuse toute réservation, donc aucun appel fournisseur, et reste
    refusé : il n'est jamais « réparé » en silence.
    """
    __slots__ = ("_ceiling", "_reserved", "_unreconciled", "_settled", "_unknown_calls", "_overruns", "_poisoned", "_lock")

    def __init__(self, ceiling_usd: float):
        if not finite_nonneg(ceiling_usd):
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "the budget ceiling must be finite and non-negative")
        self._ceiling, self._reserved, self._unreconciled, self._settled = float(ceiling_usd), {}, {}, 0.0
        self._unknown_calls, self._overruns, self._poisoned = 0, 0, False
        self._lock = threading.Lock()

    ceiling_usd = property(lambda self: self._ceiling)
    settled_usd = property(lambda self: self._settled)
    unknown_calls = property(lambda self: self._unknown_calls)
    overruns = property(lambda self: self._overruns)

    @property
    def reserved(self) -> dict:
        return dict(self._reserved) if isinstance(self._reserved, dict) else {}   # copie : muter le résultat ne change pas le budget

    @property
    def unreconciled(self) -> dict:
        """Tentatives dont le coût n'a pas pu être établi : le montant RÉSERVÉ y reste engagé jusqu'à `reconcile` (jamais compté comme 0)."""
        return dict(self._unreconciled) if isinstance(self._unreconciled, dict) else {}

    def _state_error(self) -> str | None:
        """Message décrivant l'incohérence, ou None si l'état est sain. À appeler sous verrou."""
        if self._poisoned:
            return "budget state was corrupted earlier; it stays refused"
        if not finite_nonneg(self._ceiling):
            return "budget ceiling is not finite and non-negative"
        if not finite_nonneg(self._settled):
            return "settled amount is not finite and non-negative"
        for held in (self._reserved, self._unreconciled):
            if not isinstance(held, dict) or any(not isinstance(k, str) or not finite_nonneg(v) for k, v in held.items()):
                return "a reservation is not a finite non-negative amount"
        if set(self._reserved) & set(self._unreconciled):
            return "a label is both reserved and unreconciled"
        for counter in (self._unknown_calls, self._overruns):
            if not isinstance(counter, int) or isinstance(counter, bool) or counter < 0:
                return "a counter is not a non-negative integer"
        if not finite_nonneg(self._settled + sum(self._reserved.values()) + sum(self._unreconciled.values())):
            return "committed total is not finite"
        return None

    def integrity_error(self) -> str | None:
        with self._lock:
            return self._state_error()

    def committed(self) -> float:
        with self._lock:
            error = self._state_error()
            if error:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, error)
            return self._settled + sum(self._reserved.values()) + sum(self._unreconciled.values())

    def reserve(self, label: str, max_usd: float | None) -> None:
        with self._lock:
            error = self._state_error()
            if error:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: {error}, no call")
            if self._unreconciled:   # une tentative au coût inconnu bloque TOUTE nouvelle réservation jusqu'à réconciliation explicite
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: unreconciled attempt(s) {sorted(self._unreconciled)}, no new call before an explicit reconcile")
            if not isinstance(label, str) or label in self._reserved:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, "a reservation label must be a new text label")
            if not finite_nonneg(max_usd):  # None, NaN, +-inf, négatif : le coût maximal n'est pas démontrable
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: maximum cost is unknown or invalid, no call")
            if self._settled + sum(self._reserved.values()) + max_usd > self._ceiling + 1e-12:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: {max_usd:.6f} USD would exceed the ceiling")
            self._reserved[label] = max_usd

    def release(self, label: str) -> float:
        """Libère une réservation dont il est PROUVÉ qu'aucun appel n'est parti (le chiffre est à la charge de l'appelant : le transport l'établit). N'agit que sur une
        réservation en cours : un montant réglé ou non réconcilié ne se libère jamais. Retourne le montant libéré."""
        with self._lock:
            error = self._state_error()
            if error:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label}: {error}, cannot release")
            if not isinstance(label, str) or label not in self._reserved:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, "only a pending reservation can be released")
            return self._reserved.pop(label)

    def settle(self, label: str, actual_estimate_usd: float | None) -> bool:
        """Remplace la réservation par l'estimation. Estimation inconnue OU invalide : la réservation reste ENGAGÉE comme « non réconciliée »
        (jamais comptée comme 0, jamais libérée) jusqu'à `reconcile`.

        Ne lève jamais (appelée après l'appel fournisseur) : sur état corrompu, le budget est marqué corrompu et refusera toute réservation
        suivante ; `integrity_error()` le dit. Retourne True si l'estimation DÉPASSE la réservation (dépassement enregistré, jamais masqué).
        """
        with self._lock:
            if self._state_error():
                self._poisoned = True
                return False
            held = self._reserved.pop(label, 0.0)
            if not finite_nonneg(actual_estimate_usd):
                self._unreconciled[label] = held
                self._unknown_calls += 1
                return False
            self._settled += actual_estimate_usd
            if actual_estimate_usd > held + 1e-12:
                self._overruns += 1
                return True
            return False

    def reconcile(self, label: str, actual_usd: float, *, note: str) -> None:
        """Réconciliation EXPLICITE (par une personne, d'après la facture du fournisseur) d'une tentative au coût inconnu : le montant réel remplace la réservation.
        `note` (obligatoire) dit d'où vient le montant. Un montant inférieur à la réservation libère la différence ; supérieur, il est enregistré comme dépassement."""
        with self._lock:
            error = self._state_error()
            if error:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, error)
            if label not in self._unreconciled:
                raise c.ReviewError(c.BUDGET_EXHAUSTED, f"{label} is not an unreconciled attempt")
            if not finite_nonneg(actual_usd) or not isinstance(note, str) or not note.strip():
                raise c.ReviewError(c.BUDGET_EXHAUSTED, "reconcile needs a finite non-negative amount and a note saying where it comes from")
            held = self._unreconciled.pop(label)
            self._settled += actual_usd
            if actual_usd > held + 1e-12:
                self._overruns += 1
