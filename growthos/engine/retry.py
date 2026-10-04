"""Délais de reprise pour les clés API partagées entre organisations.

ELEVENLABS_API_KEY et PEXELS_API_KEY sont globales : un 429 peut venir d'une
autre organisation qui génère en même temps, pas de ce run. On attend donc le
délai annoncé par le fournisseur (`Retry-After`) quand il existe, sinon un
backoff exponentiel avec un peu de jitter, pour que deux runs bloqués en même
temps ne repartent pas exactement ensemble.
"""
import random

_BACKOFF_CAP_SECONDS = 16.0
RETRY_AFTER_CAP_SECONDS = 30.0


def retry_delay(attempt: int, response=None, cap: float = RETRY_AFTER_CAP_SECONDS) -> float:
    """Secondes à attendre avant la tentative suivante (`attempt` = celle qui vient d'échouer, à partir de 1)."""
    header = None
    if response is not None:
        try:
            header = response.headers.get("Retry-After")
        except AttributeError:
            header = None
    try:
        provider_delay = float(header)
    except (TypeError, ValueError):
        provider_delay = None
    if provider_delay is not None and provider_delay >= 0:
        return min(provider_delay, cap)
    return min(2.0 ** attempt, _BACKOFF_CAP_SECONDS) + random.uniform(0.0, 1.0)
