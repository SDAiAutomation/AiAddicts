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
from .authorization import Window
from .tokenizer import resolve, underestimated, upper_input_tokens

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


@dataclass
class MeteredTransport:
    sender: Sender
    window: Window
    max_request_bytes: int = 256_000
    attempts: list[TransportAttempt] = field(default_factory=list)
    tripped: str | None = None

    def send(self, req: HttpRequest) -> tuple[HttpResponse | None, TransportAttempt]:
        """Un envoi, une tentative. Lève `ReviewError` (aucun appel émis) si une condition d'autorisation manque, `TransportError` après échec."""
        auth = self.window.check()
        if self.tripped:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, f"transport tripped: {self.tripped}")
        if len(self.attempts) >= auth.raw["max_logical_calls"]:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "the authorised number of provider calls is exhausted")
        if req.method != "POST" or req.host != auth.raw["provider_host"] or req.path != auth.raw["endpoint_path"]:
            raise c.ReviewError(c.BUDGET_EXHAUSTED, "request does not target the single authorised host and endpoint")
        if len(req.body) > self.max_request_bytes or not (math.isfinite(req.timeout_s) and 0 < req.timeout_s <= 300):
            raise c.ReviewError(c.INPUT_TOO_LARGE, "request body or timeout outside the allowed bounds")
        started, status, error, received, resp = time.time(), None, None, 0, None
        with measure_connects() as measured:
            try:
                resp = self.sender(req)
                status, received = resp.status, len(resp.body)
                if not 200 <= resp.status < 300:   # 3xx (redirection non suivie), 429, 5xx : échec visible, JAMAIS de nouvelle tentative
                    error = f"http_{resp.status}"
            except Exception as exc:  # noqa: BLE001 - toute panne d'émetteur est consignée telle quelle
                error = type(exc).__name__
        extra = measured.connects > 1
        attempt = TransportAttempt(
            attempt_no=len(self.attempts) + 1, host=req.host, path=req.path, started_at=started, latency_s=time.time() - started, status=status,
            connects=measured.connects, http_attempts=max(1, measured.connects), bytes_sent=len(req.body), bytes_received=received,
            request_id=(resp.headers.get("x-request-id") if resp else None), retry_after=(resp.headers.get("retry-after") if resp else None),
            error=error, extra_connection_detected=extra)
        self.attempts.append(attempt)
        if extra:
            self.tripped = "extra connection detected during a single send (hidden retry or redirect)"
        if error:
            raise TransportError(error, attempt)
        return resp, attempt


def usage_from_body(body: bytes) -> dict:
    """Jetons et coût RENVOYÉS par le fournisseur (formes `usage.prompt_tokens/completion_tokens` ou `input_tokens/output_tokens`).

    Retourne {"input", "output", "reasoning", "provider_cost_usd"} ; toute valeur absente ou invalide vaut `None` (jamais 0). Les jetons de
    raisonnement sont, chez la plupart des fournisseurs, déjà inclus dans la sortie facturée : ils sont reportés à part pour audit, pas ajoutés."""
    out = {"input": None, "output": None, "reasoning": None, "provider_cost_usd": None}
    try:
        usage = json.loads(body.decode("utf-8")).get("usage") or {}
    except (ValueError, AttributeError):
        return out
    if not isinstance(usage, dict):
        return out
    pick = lambda *keys: next((usage[k] for k in keys if finite_nonneg(usage.get(k))), None)  # noqa: E731
    out["input"], out["output"] = pick("prompt_tokens", "input_tokens"), pick("completion_tokens", "output_tokens")
    details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    out["reasoning"] = details.get("reasoning_tokens") if isinstance(details, dict) and finite_nonneg(details.get("reasoning_tokens")) else None
    out["provider_cost_usd"] = usage["cost"] if finite_nonneg(usage.get("cost")) else None
    return out


class ChatCompletionsProvider:
    """Fournisseur à l'interface de chat-completions, branché sur le transport instrumenté. Dépend du MODÈLE CHOISI : nom du paramètre de plafond de sortie
    (`max_output_param`), support d'un message système, paramètres de raisonnement. Aucun défaut n'est supposé : ils viennent de l'autorisation et de l'appelant."""

    def __init__(self, transport: MeteredTransport, *, api_key: Callable[[], str], max_output_param: str, extra_body: dict | None = None):
        self.transport, self.api_key, self.max_output_param, self.extra_body = transport, api_key, max_output_param, extra_body or {}

    def __call__(self, request: dict) -> ProviderResult:
        auth = self.transport.window.check()
        counter = resolve(auth.raw["tokenizer_id"])                      # TokenizerRequired = pas d'appel
        counted = upper_input_tokens(counter, request["system"], request["user"])
        if counted > auth.raw["max_input_tokens"]:
            raise c.ReviewError(c.INPUT_TOO_LARGE, f"prompt needs up to {counted} input tokens, authorised maximum is {auth.raw['max_input_tokens']}")
        body = {"model": auth.raw["model"], "messages": [{"role": "system", "content": request["system"]}, {"role": "user", "content": request["user"]}],
                self.max_output_param: min(request["max_output_tokens"], auth.raw["max_output_tokens"]), **self.extra_body}
        req = HttpRequest("POST", auth.raw["provider_host"], auth.raw["endpoint_path"],
                          {"content-type": "application/json", "authorization": f"Bearer {self.api_key()}"},
                          json.dumps(body, ensure_ascii=False).encode("utf-8"), float(request["timeout_s"]))
        try:
            resp, attempt = self.transport.send(req)
        except TransportError as exc:
            attempt = exc.attempt
            return ProviderResult(text=None, usage=None, error=str(exc), latency_s=attempt.latency_s if attempt else None,
                                  http_attempts=attempt.http_attempts if attempt else None)
        usage = usage_from_body(resp.body)
        try:
            text = json.loads(resp.body.decode("utf-8"))["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            text = None
        if underestimated(counted, usage["input"]):   # le compteur sous-estime : plus aucun envoi tant qu'il n'est pas corrigé
            self.transport.tripped = f"tokenizer {counter.id} counted {counted} but the provider reported {usage['input']} input tokens"
        known = usage["input"] is not None and usage["output"] is not None
        return ProviderResult(text=text if isinstance(text, str) else None, usage={"input": usage["input"], "output": usage["output"]} if known else None,
                              error=None if isinstance(text, str) else "no text in the response", latency_s=attempt.latency_s,
                              http_attempts=attempt.http_attempts, observed_cost_usd=usage["provider_cost_usd"])
