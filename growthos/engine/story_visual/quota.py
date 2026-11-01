"""Quota de jobs par locataire (fenêtre glissante). Implémentation mémoire pour tests et exécution mono-processus ;
en production le quota réel reste la réservation de crédit du worker (`repo.reserve_generation_credit`) ; un quota
partagé entre workers (base de données) est un prérequis du pilote, voir l'ADR."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


class InMemoryQuota:
    def __init__(self, limit: int, window_s: float = 86400.0, clock=time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, tenant_id: str) -> bool:
        with self._lock:
            now, hits = self.clock(), self._hits[tenant_id]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


class SharedQuota:
    """Quota de histoires par organisation PARTAGÉ entre workers : il relit la base (`product_events`, `generation_started` du moteur
    `story_visual`) au lieu d'un compteur mémoire. Les reprises d'une même histoire ne comptent qu'une fois ; l'histoire courante est exclue.
    FAIL-CLOSED : une erreur de lecture REFUSE (jamais « quota illimité »). Résiduel assumé : deux workers qui liraient au même instant peuvent
    passer ensemble ; la réservation de crédit (RPC atomique), la réclamation conditionnelle des jobs et le groupe de concurrence du workflow
    du worker bornent ce cas."""

    def __init__(self, client, organization_id: str, content_item_id: str, limit: int, window_s: float = 86400.0, now=None):
        self.client, self.organization_id, self.content_item_id = client, organization_id, content_item_id
        self.limit, self.window_s = limit, window_s
        self._now = now or (lambda: datetime.now(timezone.utc))

    def consume(self, tenant_id: str | None = None) -> bool:
        if not self.organization_id or self.limit <= 0:
            return False
        try:
            cutoff = (self._now() - timedelta(seconds=self.window_s)).isoformat()
            rows = (self.client.table("product_events").select("content_item_id")
                    .eq("organization_id", self.organization_id).eq("event", "generation_started")
                    .eq("props->>renderer", "story_visual").gte("created_at", cutoff).execute().data or [])
        except Exception:  # noqa: BLE001 - unreadable quota: refuse rather than allow unlimited paid runs
            return False
        others = {r.get("content_item_id") for r in rows if r.get("content_item_id") not in (None, self.content_item_id)}
        return len(others) < self.limit
