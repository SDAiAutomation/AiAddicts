"""Exécuteur P0-D HORS LIGNE : la chaîne d'exécution contrôlée, branchée sur un transport à émetteur factice (jamais sur un fournisseur réel).

Séquence, dans cet ordre, pour CHAQUE appel :
  autorisation (temps) -> empreintes (autorisation, tarifs, attestation, profil) -> état réseau VIVANT -> tokenizer figé -> budget (montant maximal)
  -> réservation -> vérification finale (tout, à nouveau) -> transport (créneau atomique, file d'envoi, corps validé, contrôle final, émission)
  -> comptabilisation (coût estimé, règlement) -> réconciliation (explicite, si le coût n'a pas pu être établi).

GARANTIES RÉELLES (testées)
- Aucun envoi sans fenêtre ouverte, contrôleur réseau vivant « open » attesté, empreintes inchangées, tokenizer figé inchangé : revérifiés avant la réservation ET avant l'émission.
- Une réservation n'est libérée QUE si le transport prouve qu'aucun envoi n'a eu lieu (`SendTicket.emitted` faux). Sinon le montant devient « non réconcilié » : aucun nouvel appel avant
  `reconcile` explicite, et l'exécuteur s'arrête.
- Aucun retry, jamais : un envoi = une tentative ; toute erreur après émission (délai, 429, 5xx, redirection, réponse partielle ou sans coût établi) arrête l'exécuteur.
- Arrêt global : `stop()` ou tout incident arrête l'exécuteur ET le transport ; les appels en attente sont refusés avant émission et leur réservation est libérée.
- Le plafond d'appels et le plafond monétaire tiennent sous concurrence (créneaux et réservations atomiques).

LIMITES RÉELLES (non couvertes par ce code)
- Entre le contrôle final et l'appel de l'émetteur il reste quelques instructions : une substitution à cet instant précis n'est pas détectable en Python pur. Seule la coupure réseau au
  niveau du système d'exploitation (courtier bloqué hors fenêtre, IP du fournisseur seules pendant la fenêtre) borne ce risque. Elle est PROPOSÉE (egress.py), pas appliquée ici.
- Un contrôleur réseau « simulated » (FakeEgressController) n'est PAS une preuve de coupure OS ; le rapport l'indique (`os_cutoff_proven`). Un contrôleur « os_readonly » ne vaut que ce que
  valent le lanceur de commandes injecté et la machine qui l'exécute.
- Le coût est une ESTIMATION (jetons rapportés x tarifs approuvés), pas une facture. Les jetons réellement facturés ne sont connus qu'à la réponse.
- Le code appelé par `count` du tokenizer n'est pas empreint ; le tokenizer fige la classe, l'état d'instance et le code de `count`.
- Aucune connexion réelle n'est construite ici : le fournisseur factice est l'émetteur injecté du transport.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from .. import contract as c
from ..providers import Budget, estimate_usd, max_call_usd
from .authorization import Window
from .transport import ChatCompletionsProvider, SendTicket

STEPS = ("authorization", "fingerprints", "network", "tokenizer", "budget", "reservation", "final_check", "transport", "accounting")


@dataclass(frozen=True)
class ExecResult:
    label: str
    status: str                       # completed | refused_before_send | failed_after_send | halted
    text: str | None = None
    usage: dict | None = None
    estimated_usd: float | None = None
    emitted: bool = False
    error: str | None = None
    steps: tuple = ()


@dataclass
class OfflineExecutor:
    provider: ChatCompletionsProvider
    budget: Budget
    records: list = field(default_factory=list)
    incidents: list = field(default_factory=list)
    _halted: str | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def window(self) -> Window:
        return self.provider.transport.window

    # --- arrêt ---------------------------------------------------------------------------------------------------------------------------------

    def halted(self) -> str | None:
        with self._lock:
            return self._halted

    def stop(self, reason: str = "stopped by the operator") -> None:
        """Arrêt global : plus aucune réservation ni émission, y compris pour les appels déjà en file (refusés avant émission, réservation libérée)."""
        self._halt(reason)

    def _halt(self, reason: str, label: str | None = None) -> None:
        with self._lock:
            self._halted = self._halted or reason
            self.incidents.append({"reason": reason, "label": label})
        self.provider.transport.stop(reason)

    # --- exécution -----------------------------------------------------------------------------------------------------------------------------

    def execute(self, request: dict) -> ExecResult:
        label = f"call:{uuid.uuid4().hex[:10]}"
        steps: list[str] = []
        halted = self.halted()
        if halted:
            return self._record(ExecResult(label, "halted", error=f"executor halted: {halted}", steps=tuple(steps)))
        ticket, reserved, auth = SendTicket(), False, None
        try:
            window = self.window
            auth = window.check_time(); steps.append("authorization")
            window.verify_fingerprints(); steps.append("fingerprints")
            window.verify_network(); steps.append("network")
            window.verify_tokenizer(); steps.append("tokenizer")
            amount = max_call_usd(auth.prices, auth.raw["max_input_tokens"], auth.raw["max_output_tokens"]); steps.append("budget")   # None = composante inconnue ou non plafonnée
            self.budget.reserve(label, amount); reserved = True; steps.append("reservation")
            window.check(); steps.append("final_check")                                    # tout re-vérifié : le temps a pu passer entre la réservation et l'envoi
            result = self.provider.call(request, ticket); steps.append("transport")
        except BaseException as exc:  # noqa: BLE001 - la comptabilité doit être juste même pour une interruption
            outcome = self._after_exception(label, reserved, ticket, exc, tuple(steps))
            if not isinstance(exc, Exception):   # KeyboardInterrupt, SystemExit, etc. : la comptabilité est faite, l'interruption n'est jamais avalée
                raise
            return outcome
        return self._account(label, auth, result, ticket, tuple(steps))

    def _after_exception(self, label: str, reserved: bool, ticket: SendTicket, exc: BaseException, steps: tuple) -> ExecResult:
        error = f"{type(exc).__name__}: {getattr(exc, 'message', str(exc))}"
        if ticket.emitted:
            # Un envoi a eu lieu et on n'en connaît pas le coût : montant conservé (non réconcilié), arrêt, aucun retry.
            self.budget.settle(label, None)
            self._halt("UNKNOWN_COST_AFTER_SEND", label)
            return self._record(ExecResult(label, "failed_after_send", emitted=True, error=error, steps=steps))
        if reserved:
            self.budget.release(label)    # PROUVÉ : le transport n'a jamais appelé l'émetteur
        if self.window.closed:           # une vérification a fermé la fenêtre : plus aucune exécution possible
            self._halt("WINDOW_CLOSED", label)
        return self._record(ExecResult(label, "refused_before_send", emitted=False, error=error, steps=steps))

    def _account(self, label: str, auth, result, ticket: SendTicket, steps: tuple) -> ExecResult:
        estimate = estimate_usd(result.usage, auth.prices)
        reasons = []
        if estimate is None or result.error:
            self.budget.settle(label, None)
            reasons.append("UNKNOWN_USAGE" if not result.error else "PROVIDER_ERROR_OR_INCIDENT")
        else:
            if self.budget.settle(label, estimate):
                reasons.append("COST_EXCEEDED_RESERVATION")
            if result.partial:
                reasons.append("PARTIAL_RESPONSE")
            if result.text is None:
                reasons.append("NO_RESPONSE_TEXT")
        if self.provider.transport.tripped and not reasons:
            reasons.append("TRANSPORT_TRIPPED")
        for reason in reasons:
            self._halt(reason, label)
        status = "completed" if not reasons else "failed_after_send"
        return self._record(ExecResult(label, status, text=result.text, usage=result.usage, estimated_usd=estimate, emitted=ticket.emitted, error=result.error,
                                       steps=steps + ("accounting",)))

    def _record(self, result: ExecResult) -> ExecResult:
        with self._lock:
            self.records.append(result)
        return result

    # --- réconciliation ------------------------------------------------------------------------------------------------------------------------

    def reconcile(self, label: str, actual_usd: float, *, note: str) -> None:
        """Réconciliation EXPLICITE d'une tentative au coût inconnu (facture lue par le propriétaire). N'enlève PAS l'arrêt : une nouvelle campagne demande une nouvelle fenêtre."""
        self.budget.reconcile(label, actual_usd, note=note)

    # --- rapport -------------------------------------------------------------------------------------------------------------------------------

    def report(self) -> dict:
        kind = self.window.egress_kind
        with self._lock:
            records, halted, incidents = list(self.records), self._halted, list(self.incidents)
        return {"calls": len(records), "emitted": sum(r.emitted for r in records), "completed": sum(r.status == "completed" for r in records),
                "refused_before_send": sum(r.status == "refused_before_send" for r in records), "failed_after_send": sum(r.status == "failed_after_send" for r in records),
                "halted": halted, "incidents": incidents, "settled_usd": self.budget.settled_usd, "committed_usd": self.budget.committed(),
                "unreconciled": sorted(self.budget.unreconciled), "retries": 0,
                "egress_kind": kind, "os_cutoff_proven": False,
                "network_proof": ("SIMULATED controller: NOT a proof of OS-level network cutoff" if kind == "simulated" else
                                  "read-only OS check through an injected runner: as reliable as that runner; the cutoff itself is only proposed, never applied by this code")}
