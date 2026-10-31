"""Transport instrumenté pour la future campagne : UNE tentative par appel, mesurée par le transport lui-même, jamais déclarée par le fournisseur.

- Aucun retry implicite : `send` n'a pas de boucle ; `HttpClientSender` s'appuie sur `http.client` (pas de couche de reprise, pas de suivi des redirections, pas de
  proxy d'environnement) ; 429, 5xx, délai dépassé, 3xx = échec visible.
- Tentatives RÉELLES : un crochet d'audit CPython compte les `socket.connect` ouverts PENDANT l'appel. Un émetteur qui reprend en interne (donc qui ouvre une
  deuxième connexion) est détecté même s'il déclare une seule tentative, et le transport se déclenche (`tripped`) : plus aucun envoi.
- Jetons et coût : lus dans la réponse du fournisseur (jamais calculés ici). Un coût n'est « observé » que si le fournisseur le renvoie ; sinon `None`.
- Chaque envoi exige une fenêtre d'autorisation ouverte, l'hôte et le chemin autorisés, et ne dépasse pas le nombre d'appels autorisé.
Ce module n'ouvre aucune connexion de lui-même : il faut lui fournir un émetteur et une fenêtre ouverte. Aucune clé n'est lue ici (`api_key` est injectée).
"""
from __future__ import annotations

import http.client
import json
import math
import socket
import ssl
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from .. import contract as c
from ..providers import ProviderResult, finite_nonneg
from .authorization import CampaignAuthorization, Window
from .profiles import PROTECTED, REASONING_NAMES, BodyPolicy, profile_for, validate_body
from .tokenizer import estimate_input_tokens, underestimated

MAX_RESPONSE_BYTES = 2_000_000
_counter_lock = threading.Lock()
_active_counters: list["ConnectCounter"] = []


class ConnectCounter:
    def __init__(self):
        self.connects = 0
        self.events: list[str] = []


def _audit(event: str, args) -> None:
    if event == "socket.connect" and _active_counters:
        with _counter_lock:
            for counter in _active_counters:
                counter.connects += 1
                counter.events.append(event)


sys.addaudithook(_audit)  # irrévocable ; ne fait rien tant qu'aucune mesure n'est active


@contextmanager
def measure_connects():
    """Compte les connexions socket ouvertes (tous threads du processus) pendant le bloc."""
    counter = ConnectCounter()
    with _counter_lock:
        _active_counters.append(counter)
    try:
        yield counter
    finally:
        with _counter_lock:
            _active_counters.remove(counter)


@dataclass(frozen=True)
class HttpRequest:
    method: str
    host: str
    path: str
    headers: dict
    body: bytes
    timeout_s: float


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict
    body: bytes


Sender = Callable[[HttpRequest], HttpResponse]


class TransportError(RuntimeError):
    def __init__(self, message: str, attempt: "TransportAttempt | None" = None):
        super().__init__(message)
        self.attempt = attempt


@dataclass(frozen=True)
class TransportAttempt:
    """Une ligne du journal de transport : ce qui s'est RÉELLEMENT passé, mesuré ici."""
    attempt_no: int
    host: str
    path: str
    started_at: float
    latency_s: float
    status: int | None
    connects: int                      # connexions socket observées pendant l'appel (mesure indépendante de l'émetteur)
    http_attempts: int                 # max(1, connexions mesurées) : jamais inférieur à la réalité observée
    bytes_sent: int
    bytes_received: int
    request_id: str | None
    retry_after: str | None
    error: str | None
    extra_connection_detected: bool


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Se connecte à une ADRESSE IP fournie par le propriétaire (aucune résolution DNS : le pare-feu du courtier n'autorise pas le DNS) mais vérifie le certificat et
    envoie le SNI pour le NOM d'hôte autorisé. Un certificat qui ne correspond pas à ce nom est refusé."""

    def __init__(self, host, ip, port, *, timeout, context):
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class HttpClientSender:
    """Émetteur `http.client` à UNE tentative. En production : `tls=True` et `connect_override=(IP du fournisseur, 443)` (IP relevée par le propriétaire, voir egress.py).
    `tls=False` ne sert qu'aux tests sur la boucle locale. `ssl_context` permet aux tests de faire confiance à un certificat auto-signé."""

    def __init__(self, *, tls: bool = True, connect_override: tuple[str, int] | None = None, ssl_context: ssl.SSLContext | None = None):
        self.tls, self.connect_override, self.ssl_context = tls, connect_override, ssl_context

    def __call__(self, req: HttpRequest) -> HttpResponse:
        if self.tls and self.connect_override:
            ip, port = self.connect_override
            conn = _PinnedHTTPSConnection(req.host, ip, port, timeout=req.timeout_s, context=self.ssl_context or ssl.create_default_context())
        else:
            host, port = self.connect_override or (req.host, 443 if self.tls else 80)
            conn = (http.client.HTTPSConnection if self.tls else http.client.HTTPConnection)(host, port, timeout=req.timeout_s)
        try:
            conn.request(req.method, req.path, body=req.body, headers={**req.headers, "Host": req.host})
            resp = conn.getresponse()
            body = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise TransportError("response too large")
            return HttpResponse(resp.status, {k.lower(): v for k, v in resp.getheaders()}, body)
        finally:
            conn.close()




BodyValidator = Callable[[HttpRequest, "CampaignAuthorization"], None]


def profile_body_validator(req: HttpRequest, auth: CampaignAuthorization) -> None:
    """Validateur par défaut : le corps EXACT est validé contre le profil du modèle autorisé (liste explicite de paramètres). Modèle inconnu = `ModelUnknown`."""
    validate_body(req.body, model=auth.raw["model"], max_output_tokens=auth.raw["max_output_tokens"], profile=profile_for(auth.raw["model"]),
                  reasoning_cap_tokens=auth.raw.get("reasoning_cap_tokens"))


@dataclass
class SendTicket:
    """Preuve d'émission d'UN envoi : `emitted` passe à True juste avant l'appel de l'émetteur, jamais avant. Tant qu'il est False, il est PROUVÉ que rien n'est parti ;
    une fois True, rien ne peut le prouver à nouveau : le coût est inconnu jusqu'à réconciliation. Posé par le transport, lu par l'exécuteur."""
    emitted: bool = False
    before_emit: "Callable[[], None] | None" = None   # exécuté juste avant l'émetteur (journal durable `sending`) ; s'il lève, rien n'est émis


@dataclass
class MeteredTransport:
    """Une tentative par envoi, plafond d'appels ATOMIQUE.

    Réservation d'un créneau (compteur sous verrou) AVANT tout envoi : N threads concurrents ne peuvent pas dépasser `max_logical_calls`, même si le fournisseur répond
    lentement. Les envois sont sérialisés (un seul en vol) : la mesure des connexions est exacte. Un créneau est RENDU seulement si rien n'a été émis (refus de validation,
    fenêtre expirée pendant l'attente, arrêt demandé, file d'attente expirée) ; dès que l'émetteur est appelé, il est consommé, même en cas d'exception ou de délai dépassé.
    `body_validator` est OBLIGATOIRE : sans lui, aucun envoi."""
    sender: Sender
    window: Window
    body_validator: BodyValidator | None = None
    max_request_bytes: int = 256_000
    max_queue_wait_s: float = 600.0
    attempts: list[TransportAttempt] = field(default_factory=list)
    tripped: str | None = None
    _slots: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _send_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def stop(self, reason: str = "stopped by the operator") -> None:
        """Arrêt : l'envoi en cours se termine, tout envoi en attente ou futur est refusé (son créneau est rendu, rien n'est émis)."""
        with self._lock:
            self.tripped = self.tripped or reason

    def slots_used(self) -> int:
        with self._lock:
            return self._slots

    def _refuse(self, message: str, code: str = c.BUDGET_EXHAUSTED):
        raise c.ReviewError(code, message)

    def send(self, req: HttpRequest, ticket: SendTicket | None = None) -> tuple[HttpResponse | None, TransportAttempt]:
        """Un envoi, une tentative. Lève `ReviewError` (aucun appel émis) si une condition manque, `TransportError` après échec.

        Ordre : contrôle complet de la fenêtre -> créneau atomique -> file d'envoi -> contrôle complet -> validation du corps -> contrôle FINAL -> émission. Le contrôle final est la
        DERNIÈRE chose faite avant l'appel de l'émetteur ; il reste un intervalle (quelques instructions) entre lui et l'appel : seule la coupure réseau au niveau du système
        d'exploitation le couvre réellement."""
        auth = self.window.check()
        if self.body_validator is None:
            self._refuse("no body validator configured: no send")
        if req.method != "POST" or req.host != auth.raw["provider_host"] or req.path != auth.raw["endpoint_path"]:
            self._refuse("request does not target the single authorised host and endpoint")
        if len(req.body) > self.max_request_bytes or not (isinstance(req.timeout_s, (int, float)) and math.isfinite(req.timeout_s) and 0 < req.timeout_s <= 300):
            self._refuse("request body or timeout outside the allowed bounds", c.INPUT_TOO_LARGE)
        with self._lock:  # RÉSERVATION ATOMIQUE du créneau, avant tout envoi
            if self.tripped:
                self._refuse(f"transport tripped: {self.tripped}")
            if self._slots >= auth.raw["max_logical_calls"]:
                self._refuse("the authorised number of provider calls is exhausted")
            self._slots += 1
        emitted = False
        try:
            if not self._send_lock.acquire(timeout=self.max_queue_wait_s):
                self._refuse("the send queue timed out: nothing was sent")
            try:
                auth = self.window.check()                       # la fenêtre a pu expirer pendant l'attente
                with self._lock:
                    if self.tripped:
                        self._refuse(f"transport tripped: {self.tripped}")
                self.body_validator(req, auth)                   # corps EXACT validé immédiatement avant l'envoi
                self.window.check()                              # contrôle FINAL : tout ce qui a pu changer pendant l'attente ou la validation (temps, profil, tarifs, tokenizer, réseau)
                with self._lock:
                    if self.tripped:
                        self._refuse(f"transport tripped: {self.tripped}")
                if ticket is not None and ticket.before_emit is not None:
                    ticket.before_emit()                         # marqueur durable AVANT l'émission : en cas d'échec, rien n'est parti
                emitted = True                                   # à partir d'ici le créneau est consommé quoi qu'il arrive
                if ticket is not None:
                    ticket.emitted = True
                started, status, error, received, resp = time.time(), None, None, 0, None
                with measure_connects() as measured:
                    try:
                        resp = self.sender(req)
                        status, received = resp.status, len(resp.body)
                        if not 200 <= resp.status < 300:         # 3xx (redirection non suivie), 429, 5xx : échec visible, JAMAIS de nouvelle tentative
                            error = f"http_{resp.status}"
                    except Exception as exc:  # noqa: BLE001 - toute panne d'émetteur est consignée telle quelle
                        error = type(exc).__name__
                extra = measured.connects > 1
                with self._lock:
                    attempt = TransportAttempt(
                        attempt_no=len(self.attempts) + 1, host=req.host, path=req.path, started_at=started, latency_s=time.time() - started, status=status,
                        connects=measured.connects, http_attempts=max(1, measured.connects), bytes_sent=len(req.body), bytes_received=received,
                        request_id=(resp.headers.get("x-request-id") if resp else None), retry_after=(resp.headers.get("retry-after") if resp else None),
                        error=error, extra_connection_detected=extra)
                    self.attempts.append(attempt)
                    if extra:
                        self.tripped = self.tripped or "extra connection detected during a single send (hidden retry or redirect)"
                    if error:   # ATOMIQUE avec l'enregistrement de la tentative : aucun envoi en file ne peut partir après un échec dont le coût est inconnu
                        self.tripped = self.tripped or f"attempt failed ({error}): no further send"
            finally:
                self._send_lock.release()
        except BaseException:
            if not emitted:
                with self._lock:
                    self._slots -= 1                              # rien n'est parti : le créneau est rendu
            raise
        if error:
            raise TransportError(error, attempt)
        return resp, attempt


def usage_from_body(body: bytes) -> dict:
    """Jetons, coût et fin de réponse RENVOYÉS par le fournisseur (formes `usage.prompt_tokens/completion_tokens` ou `input_tokens/output_tokens`).

    Retourne {"input", "output", "reasoning", "provider_cost_usd", "finish_reason"} ; toute valeur absente ou invalide vaut `None` (jamais 0). Selon le fournisseur, les jetons de
    raisonnement sont déjà inclus dans la sortie facturée ou facturés à part : la politique du modèle (`reasoning_policy`) tranche, ils sont ici reportés tels quels pour audit."""
    out = {"input": None, "output": None, "reasoning": None, "provider_cost_usd": None, "finish_reason": None}
    try:
        data = json.loads(body.decode("utf-8"))
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        out["finish_reason"] = choice.get("finish_reason") if isinstance(choice, dict) and isinstance(choice.get("finish_reason"), str) else None
    except (ValueError, AttributeError, IndexError, TypeError):
        return out
    if not isinstance(usage, dict):
        return out
    pick = lambda *keys: next((usage[k] for k in keys if finite_nonneg(usage.get(k))), None)  # noqa: E731
    out["input"], out["output"] = pick("prompt_tokens", "input_tokens"), pick("completion_tokens", "output_tokens")
    details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    out["reasoning"] = details.get("reasoning_tokens") if isinstance(details, dict) and finite_nonneg(details.get("reasoning_tokens")) else None
    out["provider_cost_usd"] = usage["cost"] if finite_nonneg(usage.get("cost")) else None
    return out


COMPLETE_FINISH_REASONS = ("stop", "end_turn")


class ChatCompletionsProvider:
    """Fournisseur à l'interface de chat-completions, branché sur le transport instrumenté. Tout ce qui dépend du MODÈLE vient de son PROFIL (`profiles.py`) : sans profil, aucun appel.

    Le corps est construit à partir de clés FIXES (model, messages, plafond de sortie) ; `extra_body` ne peut ni remplacer une clé fixe, ni introduire un paramètre protégé ou non listé :
    toute collision ou clé inconnue lève une erreur au lieu d'être écrasée en silence. Le corps final est ensuite validé octet par octet par le transport."""

    def __init__(self, transport: MeteredTransport, *, api_key: Callable[[], str], extra_body: dict | None = None):
        self.transport, self.api_key, self.extra_body = transport, api_key, dict(extra_body or {})
        if self.transport.body_validator is None:
            self.transport.body_validator = profile_body_validator

    def __call__(self, request: dict) -> ProviderResult:
        return self.call(request)

    def call(self, request: dict, ticket: SendTicket | None = None) -> ProviderResult:
        auth = self.transport.window.check()
        profile = self.transport.window.pinned_profile()                 # profil et compteur FIGÉS à l'ouverture, jamais re-résolus dans les registres
        counter = self.transport.window.pinned_counter()
        estimate = estimate_input_tokens(counter, request["system"], request["user"])
        if estimate > auth.raw["max_input_tokens"]:
            raise c.ReviewError(c.INPUT_TOO_LARGE, f"prompt is estimated at {estimate} input tokens, authorised maximum is {auth.raw['max_input_tokens']}")
        body = {"model": auth.raw["model"], "messages": [{"role": "system", "content": request["system"]}, {"role": "user", "content": request["user"]}],
                profile.max_output_param: min(request["max_output_tokens"], auth.raw["max_output_tokens"])}
        if profile.reasoning_policy == "separate_cap":                    # plafond de raisonnement : construit depuis l'autorisation, jamais depuis l'appelant
            body[profile.reasoning_param] = auth.raw["reasoning_cap_tokens"]
        for key, value in self.extra_body.items():
            if key in body or key in PROTECTED or key in REASONING_NAMES or key not in profile.allowed_extra:
                raise c.ReviewError(c.INVALID_RESPONSE, f"extra parameter {key!r} is protected, already controlled by the campaign, or not allowlisted for this model")
            body[key] = value
        req = HttpRequest("POST", auth.raw["provider_host"], auth.raw["endpoint_path"],
                          {"content-type": "application/json", "authorization": f"Bearer {self.api_key()}"},
                          json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"), float(request["timeout_s"]))
        try:
            resp, attempt = self.transport.send(req, ticket)
        except TransportError as exc:
            attempt = exc.attempt
            return ProviderResult(text=None, usage=None, error=str(exc), latency_s=attempt.latency_s if attempt else None,
                                  http_attempts=attempt.http_attempts if attempt else None)
        usage = usage_from_body(resp.body)
        try:
            text = json.loads(resp.body.decode("utf-8"))["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            text = None
        incident = self._billing_incident(auth, profile, usage, estimate)
        if incident:                                                      # le transport se déclenche : plus aucun envoi tant qu'un humain n'a pas tranché
            self.transport.stop(incident)
        known = usage["input"] is not None and usage["output"] is not None and not incident
        result_usage = {"input": usage["input"], "output": usage["output"]} if known else None
        if known and profile.reasoning_policy == "separate_cap":
            result_usage["reasoning"] = usage["reasoning"] if usage["reasoning"] is not None else 0
            if usage["reasoning"] is None:                                # unité facturable distincte non renvoyée : le coût n'est pas établi
                result_usage = None
        partial = usage["finish_reason"] not in COMPLETE_FINISH_REASONS
        return ProviderResult(text=text if isinstance(text, str) else None, usage=result_usage,
                              error=incident or (None if isinstance(text, str) else "no text in the response"), latency_s=attempt.latency_s,
                              http_attempts=attempt.http_attempts, observed_cost_usd=usage["provider_cost_usd"], partial=partial)

    @staticmethod
    def _billing_incident(auth: CampaignAuthorization, profile: BodyPolicy, usage: dict, estimate: int) -> str | None:
        """Incident de facturation visible dans la réponse : le compteur sous-estime, ou une unité facturable dépasse son plafond autorisé."""
        if underestimated(estimate, usage["input"]):
            return f"the provider reported {usage['input']} input tokens, above the estimate of {estimate}: the tokenizer underestimates"
        if usage["output"] is not None and usage["output"] > auth.raw["max_output_tokens"] + (auth.raw.get("reasoning_cap_tokens", 0) if profile.reasoning_policy == "separate_cap" else 0):
            return f"the provider reported {usage['output']} output tokens, above the authorised cap"
        reasoning = usage["reasoning"]
        if reasoning is not None:
            if profile.reasoning_policy == "not_supported_by_model" and reasoning > 0:
                return "reasoning tokens were billed although the model profile says it has none"
            if profile.reasoning_policy == "included_in_max_output" and usage["output"] is not None and reasoning > usage["output"]:
                return "reasoning tokens exceed the reported output tokens although they should be included in it"
            if profile.reasoning_policy == "separate_cap" and reasoning > auth.raw["reasoning_cap_tokens"]:
                return f"reasoning tokens ({reasoning}) exceed the authorised cap ({auth.raw['reasoning_cap_tokens']})"
        return None
