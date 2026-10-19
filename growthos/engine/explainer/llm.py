"""Appels Claude de l'Explainer : un seul point d'entrée, avec suivi de tokens, coût estimé et plafond de budget.

La clé vient de l'environnement (`ANTHROPIC_API_KEY`, chargée depuis `.env` par python-dotenv par l'appelant) : elle
n'est jamais lue, affichée ni journalisée ici. Les tarifs sont des ESTIMATIONS (cache de la documentation Claude du
2026-10-06, à revérifier) ; un modèle absent de la table a un coût INCONNU (None), jamais 0.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

DIRECTOR_MODEL = os.environ.get("EXPLAINER_DIRECTOR_MODEL", "claude-opus-5-5")
ANIMATOR_MODEL = os.environ.get("EXPLAINER_ANIMATOR_MODEL", "claude-sonnet-5-5")
COMPOSER_MODEL = os.environ.get("EXPLAINER_COMPOSER_MODEL", ANIMATOR_MODEL)   # mode gabarits : un seul appel batché, le modèle courant suffit
DEFAULT_BUDGET_USD = 1.20

# USD par million de tokens : (entrée, sortie, lecture de cache, écriture de cache 5 min)
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


# Coût maximal plausible d'un appel : on refuse de le lancer s'il ferait dépasser le plafond (appels parallèles compris).
CALL_RESERVE_USD = {"claude-opus-5-5": 0.20, "claude-sonnet-5-5": 0.07, "claude-haiku-5-5": 0.02}


STREAM_ATTEMPTS = 3


def is_transient(exc: BaseException) -> bool:
    """Coupure réseau, délai dépassé, limite de débit ou erreur serveur : on réessaie. Le reste (clé, requête invalide) remonte."""
    if type(exc).__module__.split(".")[0].startswith("httpx"):   # httpx2.RemoteProtocolError, ReadTimeout...
        return True
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError, anthropic.InternalServerError))


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Spend:
    """Compteur partagé par toutes les étapes d'une vidéo."""
    limit_usd: float = DEFAULT_BUDGET_USD
    calls: list[dict] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return round(sum(c["costUsd"] for c in self.calls if c["costUsd"] is not None), 4)

    @property
    def has_unknown_cost(self) -> bool:
        return any(c["costUsd"] is None for c in self.calls)

    def check(self, reserve: float = 0.0) -> None:
        if self.total_usd + reserve >= self.limit_usd:
            raise BudgetExceeded(f"budget LLM atteint : {self.total_usd:.2f} $ sur {self.limit_usd:.2f} $ (réserve {reserve:.2f} $)")

    def record(self, step: str, model: str, usage) -> dict:
        fresh, out = usage.input_tokens or 0, usage.output_tokens or 0
        cread, cwrite = getattr(usage, "cache_read_input_tokens", 0) or 0, getattr(usage, "cache_creation_input_tokens", 0) or 0
        price = PRICES.get(model)
        cost = None if price is None else round((fresh * price[0] + out * price[1] + cread * price[2] + cwrite * price[3]) / 1e6, 5)
        entry = {"step": step, "model": model, "inputTokens": fresh, "outputTokens": out, "cacheReadTokens": cread,
                 "cacheWriteTokens": cwrite, "costUsd": cost}
        self.calls.append(entry)
        return entry

    def report(self) -> dict:
        by_step: dict[str, float] = {}
        for c in self.calls:
            by_step[c["step"]] = round(by_step.get(c["step"], 0.0) + (c["costUsd"] or 0.0), 4)
        return {"limitUsd": self.limit_usd, "totalUsd": self.total_usd, "unknownCost": self.has_unknown_cost,
                "byStep": by_step, "calls": self.calls, "pricesAreEstimates": True}


_client = None


def client():
    global _client
    if _client is None:
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY manquant (variable d'environnement ou .env)")
        _client = anthropic.Anthropic(max_retries=3)
    return _client


def complete(spend: Spend, step: str, model: str, system: str, user, max_tokens: int = 16000, effort: str = "medium") -> str:
    """Un appel Claude en streaming ; le prompt système est mis en cache. `user` : texte, ou liste de blocs de contenu
    (texte + images base64 pour le critique). Renvoie le texte de la réponse."""
    spend.check(CALL_RESERVE_USD.get(model, 0.10))
    message, last = None, None
    for attempt in range(1, STREAM_ATTEMPTS + 1):
        try:
            with client().messages.stream(
                model=model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort},
            ) as stream:
                message = stream.get_final_message()
            break
        except Exception as exc:  # noqa: BLE001 — seules les erreurs réseau/serveur sont reprises
            if not is_transient(exc):
                raise
            last = exc
            time.sleep(2.0 * attempt)
    if message is None:
        # Un flux coupé en cours de route n'a pas de `usage` : son coût éventuel est INCONNU (non compté), pas nul.
        raise RuntimeError(f"réseau Claude indisponible après {STREAM_ATTEMPTS} essais ({step}) : {type(last).__name__}")
    spend.record(step, model, message.usage)
    if message.stop_reason == "refusal":
        raise RuntimeError("Claude a refusé la demande (refusal)")
    if message.stop_reason == "max_tokens":
        raise RuntimeError(f"réponse tronquée à {max_tokens} tokens ({step})")
    return "".join(b.text for b in message.content if b.type == "text")


def extract_json(text: str) -> dict:
    """Premier objet JSON de la réponse (avec ou sans bloc ```json)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text[text.index("{"): text.rindex("}") + 1]
    return json.loads(raw)


def extract_code(text: str) -> str:
    fenced = re.search(r"```(?:js|javascript)?\s*\n(.*?)```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()
