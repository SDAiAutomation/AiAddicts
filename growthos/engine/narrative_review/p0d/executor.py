"""Exécuteur P0-D HORS LIGNE : la chaîne d'exécution contrôlée, branchée sur un transport à émetteur factice (jamais sur un fournisseur réel).

UNE SEULE TENTATIVE EN VOL PAR CAMPAGNE. Toute la transaction d'un appel se déroule dans la SECTION CRITIQUE DE LA CAMPAGNE (`CampaignLedger.critical_section`, partagée par toutes les instances
d'exécuteur et de transport du processus ; un verrou de fichier du système interdit un second processus propriétaire) :

  décision de la tentative précédente (campagne bloquée ? tentative non résolue ?) -> autorisation (temps) -> empreintes -> état réseau vivant -> tokenizer figé
  -> budget (maximum d'un appel) -> RÉSERVATION DURABLE (journal) + miroir en mémoire -> vérification finale -> marqueur durable `sending` -> émission
  -> analyse de la réponse -> comptabilisation (`settled`) ou incident (`unreconciled`, campagne bloquée) -> décision d'autoriser ou de bloquer la suivante -> fin de la section critique.

Une deuxième tentative n'entre dans la section qu'après la résolution complète de la précédente ; elle voit alors l'éventuel blocage et ne réserve rien.

GARANTIES RÉELLES (testées)
- Au plus une tentative non résolue à tout instant, y compris entre plusieurs exécuteurs du même processus et (via le journal et le verrou de fichier) entre processus.
- La réservation est écrite durablement AVANT tout envoi, `sending` juste avant l'émission. Après un crash : `reserved` -> libérée (prouvé non envoyé), `sending` -> `unreconciled` et campagne bloquée
  jusqu'à `reconcile` puis `clear_halt` explicites.
- Aucun retry. Toute issue incertaine (coût inconnu, délai, interruption, réponse partielle) bloque la campagne et conserve la réservation.
- Une réservation n'est libérée QUE depuis l'état `reserved` : le journal refuse de libérer une tentative qui a atteint `sending`.
- Plafond d'appels et plafond monétaire tenus durablement (journal) et en mémoire.

LIMITES RÉELLES
- Entre le contrôle final / le marqueur `sending` et l'appel de l'émetteur il reste quelques instructions ; seule la coupure réseau au niveau de l'OS borne une substitution à cet instant. Elle est PROPOSÉE
  (egress.py), pas appliquée ici.
- Un contrôleur réseau « simulated » n'est PAS une preuve de coupure OS ; le rapport l'indique (`os_cutoff_proven`).
- La garantie vaut pour les processus qui passent par ce module : elle ne protège pas d'un processus qui écrit directement dans le fichier du journal, ni de sa suppression.
- Le coût est une ESTIMATION (jetons rapportés x tarifs approuvés), pas une facture. La comptabilité en mémoire (`Budget`) est un MIROIR local : le journal décide.
- Le tokenizer est empreint (classe, état, code de `count` et dépendances Python atteignables) : cela détecte les remplacements accidentels ou simples, pas un code hostile dans le même processus.
- Aucune connexion réelle n'est construite ici : le fournisseur factice est l'émetteur injecté du transport.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .. import contract as c
from ..providers import Budget, estimate_usd, max_call_usd
from .authorization import Window
from .ledger import CampaignLedger
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
    ledger: CampaignLedger
    fault_hook: Callable[[str], None] | None = None     # injection de panne pour les tests ("before_emit", "after_mark_sending", "before_accounting")
    records: list = field(default_factory=list)
    incidents: list = field(default_factory=list)
    _halted: str | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self):
        snapshot = self.ledger.snapshot()                  # miroir local remis en état depuis le journal (redémarrage)
        self.budget.restore(snapshot["settled_usd"], snapshot["unreconciled"])

    @property
    def window(self) -> Window:
        return self.provider.transport.window

    # --- arrêt ---------------------------------------------------------------------------------------------------------------------------------

    def halted(self) -> str | None:
        with self._lock:
            local = self._halted
        return local or self.ledger.halted()

    def stop(self, reason: str = "stopped by the operator") -> None:
        """Arrêt global DURABLE : plus aucune réservation ni émission ; ne prend pas la section critique (peut arrêter une tentative en attente)."""
        self._halt(reason)

    def _halt(self, reason: str, label: str | None = None) -> None:
        with self._lock:
            self._halted = self._halted or reason
            self.incidents.append({"reason": reason, "label": label})
        self.ledger.halt(reason)
        self.provider.transport.stop(reason)

    def _fault(self, point: str) -> None:
        if self.fault_hook is not None:
            self.fault_hook(point)

    # --- exécution -----------------------------------------------------------------------------------------------------------------------------

    def execute(self, request: dict) -> ExecResult:
        label = f"call:{uuid.uuid4().hex[:10]}"
        with self.ledger.critical_section():
            return self._execute_locked(label, request)

    def _execute_locked(self, label: str, request: dict) -> ExecResult:
        steps: list[str] = []
        halted = self.halted()
        if halted or self.ledger.unresolved():            # décision sur la tentative précédente : une issue non résolue ou un blocage interdit toute réservation
            return self._record(ExecResult(label, "halted", error=f"campaign blocked: {halted or 'unresolved attempt ' + str(self.ledger.unresolved())}", steps=tuple(steps)))
        ticket, durable, mirrored, auth = SendTicket(), False, False, None
        try:
            window = self.window
            auth = window.check_time(); steps.append("authorization")
            window.verify_fingerprints(); steps.append("fingerprints")
            window.verify_network(); steps.append("network")
            window.verify_tokenizer(); steps.append("tokenizer")
            amount = max_call_usd(auth.prices, auth.raw["max_input_tokens"], auth.raw["max_output_tokens"]); steps.append("budget")   # None = composante inconnue ou non plafonnée
            self.ledger.begin_attempt(label, amount); durable = True                      # DURABLE avant tout envoi
            self.budget.reserve(label, amount); mirrored = True; steps.append("reservation")
            window.check(); steps.append("final_check")                                    # tout re-vérifié : le temps a pu passer entre la réservation et l'envoi
            ticket.before_emit = lambda: self._mark_sending(label)
            result = self.provider.call(request, ticket); steps.append("transport")
            self._fault("before_accounting")
        except BaseException as exc:  # noqa: BLE001 - la comptabilité doit être juste même pour une interruption
            outcome = self._after_exception(label, durable, mirrored, ticket, exc, tuple(steps))
            if not isinstance(exc, Exception):   # KeyboardInterrupt, SystemExit, etc. : la comptabilité est faite, l'interruption n'est jamais avalée
                raise
            return outcome
        return self._account(label, auth, result, ticket, tuple(steps))

    def _mark_sending(self, label: str) -> None:
        self._fault("before_emit")
        self.ledger.mark_sending(label)
        self._fault("after_mark_sending")

    def _after_exception(self, label: str, durable: bool, mirrored: bool, ticket: SendTicket, exc: BaseException, steps: tuple) -> ExecResult:
        error = f"{type(exc).__name__}: {getattr(exc, 'message', str(exc))}"
        state = self.ledger.state_of(label) if durable else None
        if ticket.emitted or state == "sending":
            # Un envoi a eu lieu (ou n'est pas prouvé absent) et on n'en connaît pas le coût : montant conservé, campagne bloquée, aucun retry.
            self.ledger.mark_unreconciled(label, "UNKNOWN_COST_AFTER_SEND")
            if mirrored:
                self.budget.settle(label, None)
            self._halt("UNKNOWN_COST_AFTER_SEND", label)
            return self._record(ExecResult(label, "failed_after_send", emitted=ticket.emitted, error=error, steps=steps))
        if state == "reserved":
            self.ledger.release(label)       # PROUVÉ : le marqueur `sending` n'a jamais été écrit, l'émetteur n'a jamais été appelé
        if mirrored:
            self.budget.release(label)
        if self.window.closed:               # une vérification a fermé la fenêtre : plus aucune exécution possible
            self._halt("WINDOW_CLOSED", label)
        return self._record(ExecResult(label, "refused_before_send", emitted=False, error=error, steps=steps))

    def _account(self, label: str, auth, result, ticket: SendTicket, steps: tuple) -> ExecResult:
        estimate = estimate_usd(result.usage, auth.prices)
        reasons = []
        if estimate is None or result.error:
            self.ledger.mark_unreconciled(label, "UNKNOWN_USAGE" if not result.error else "PROVIDER_ERROR_OR_INCIDENT")
            self.budget.settle(label, None)
            reasons.append("UNKNOWN_USAGE" if not result.error else "PROVIDER_ERROR_OR_INCIDENT")
        else:
            self.ledger.settle(label, estimate)
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
        """Réconciliation EXPLICITE et DURABLE d'une tentative au coût inconnu (facture lue par le propriétaire). Ne débloque PAS la campagne (`ledger.clear_halt`, explicite)."""
        self.ledger.reconcile(label, actual_usd, note)       # transaction unique : tout ou rien
        try:
            self.budget.reconcile(label, actual_usd, note=note)
        except c.ReviewError:
            pass                                             # miroir local qui ne connaît pas cette tentative (autre instance, autre processus) : le journal fait foi

    # --- rapport -------------------------------------------------------------------------------------------------------------------------------

    def report(self) -> dict:
        kind = self.window.egress_kind
        with self._lock:
            records, incidents = list(self.records), list(self.incidents)
        durable = self.ledger.snapshot()
        return {"calls": len(records), "emitted": sum(r.emitted for r in records), "completed": sum(r.status == "completed" for r in records),
                "refused_before_send": sum(r.status == "refused_before_send" for r in records), "failed_after_send": sum(r.status == "failed_after_send" for r in records),
                "halted": self.halted(), "incidents": incidents, "settled_usd": durable["settled_usd"], "committed_usd": durable["committed_usd"],
                "unreconciled": sorted(durable["unreconciled"]), "durable_emitted": durable["emitted"], "retries": 0,
                "egress_kind": kind, "os_cutoff_proven": False,
                "network_proof": ("SIMULATED controller: NOT a proof of OS-level network cutoff" if kind == "simulated" else
                                  "read-only OS check through an injected runner: as reliable as that runner; the cutoff itself is only proposed, never applied by this code")}
