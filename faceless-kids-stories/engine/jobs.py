"""Registre en mémoire des jobs de génération (file d'attente asynchrone de l'API)."""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    story_path: str
    status: JobStatus = JobStatus.PENDING
    step: str = "queued"
    detail: str = "En attente de traitement"
    result_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "story_path": self.story_path,
            "status": self.status.value,
            "step": self.step,
            "detail": self.detail,
            "result_path": self.result_path,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobStore:
    """Registre des jobs en mémoire, thread-safe (pas de persistance entre redémarrages)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}
        self._counter = itertools.count(1)

    def create(self, story_path: str) -> Job:
        with self._lock:
            job_id = f"job_{next(self._counter):06d}"
            job = Job(id=job_id, story_path=story_path)
            self._jobs[job_id] = job
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> List[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at)

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = _now()
