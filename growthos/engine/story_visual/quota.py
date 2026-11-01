"""Quota de jobs par locataire (fenêtre glissante). Implémentation mémoire pour tests et exécution mono-processus ;
en production le quota réel reste la réservation de crédit du worker (`repo.reserve_generation_credit`) ; un quota
partagé entre workers (base de données) est un prérequis du pilote, voir l'ADR."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


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
