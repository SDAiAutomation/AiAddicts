"""Frontière d'exécution HORS LIGNE du harness P0, vérifiable par un test qui tente réellement un accès réseau.

Deux couches, qu'il ne faut pas confondre :
1. `OfflineProvider` : le runner refuse tout fournisseur qui n'est pas explicitement déclaré hors ligne. C'est une DÉCLARATION, donc pas
   une garantie : n'importe qui peut envelopper une fonction HTTP. Elle sert à rendre une confusion accidentelle impossible.
2. `network_denied()` : pendant toute la campagne, un crochet d'audit CPython (`sys.addaudithook`, irrévocable, déclenché par le noyau de
   l'interpréteur et non par un monkeypatch contournable) lève `OfflineViolation` sur toute résolution DNS, connexion, émission de
   datagramme, ouverture d'écoute, lancement de sous-processus, appel `os.system`/`exec`/`spawn` ou chargement de bibliothèque native.

Limite assumée : ce n'est PAS un bac à sable du système d'exploitation. Une extension native déjà chargée qui ouvre ses propres sockets sans
passer par `socket` n'est pas interceptée. Avant le moindre fournisseur réel (P0-D), il faut en plus une coupure de sortie au niveau OS
(pare-feu ou processus sans réseau) : ce module ne le remplace pas.
"""
from __future__ import annotations

import sys
import threading
from contextlib import contextmanager

BLOCKED_EVENTS = frozenset({
    "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo", "socket.connect", "socket.sendto",
    "socket.sendmsg", "socket.bind", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "ctypes.dlopen",
})

_lock = threading.Lock()
_active = 0
_violations: list[str] = []


class OfflineViolation(RuntimeError):
    """Un fournisseur ou le code qu'il appelle a tenté un accès réseau ou un contournement pendant une campagne hors ligne."""


def _audit(event: str, args) -> None:
    if _active and event in BLOCKED_EVENTS:
        _violations.append(event)
        raise OfflineViolation(f"offline campaign: {event} is forbidden")


sys.addaudithook(_audit)  # irrévocable ; ne coûte qu'un test d'entier tant qu'aucune campagne n'est active


@contextmanager
def network_denied():
    """Actif pour tous les threads du processus tant qu'une campagne tourne (compteur, donc imbriquable)."""
    global _active
    with _lock:
        _active += 1
    try:
        yield
    finally:
        with _lock:
            _active -= 1


def violations_count() -> int:
    return len(_violations)


def is_active() -> bool:
    return _active > 0


class OfflineProvider:
    """Fournisseur déclaré HORS LIGNE (factice). Seul type accepté par `run_campaign`."""

    def __init__(self, fn, *, name: str = "offline"):
        if not callable(fn):
            raise TypeError("an offline provider wraps a callable")
        self._fn, self.name = fn, name

    def __call__(self, request: dict):
        return self._fn(request)

    def __getattr__(self, item):  # expose `requests` et autres traces du fournisseur factice
        return getattr(self._fn, item)


def offline(fn, *, name: str = "offline") -> OfflineProvider:
    return fn if isinstance(fn, OfflineProvider) else OfflineProvider(fn, name=name)
