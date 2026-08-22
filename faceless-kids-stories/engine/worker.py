"""Worker en arrière-plan qui consomme la file de jobs et exécute le pipeline.

Traite les jobs un par un dans un thread dédié : suffisant pour ce moteur minimal
(voir la limite « pas de parallélisation » dans le README) et sans dépendance
externe (pas de Redis/Celery).
"""
from __future__ import annotations

import queue
import threading
import traceback
from typing import Optional

from .jobs import JobStatus, JobStore
from .pipeline import generate_story


class JobWorker:
    def __init__(self, store: JobStore) -> None:
        self.store = store
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            self._process(job_id)

    def _process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return

        self.store.update(job_id, status=JobStatus.RUNNING, step="starting", detail="Démarrage du pipeline")

        def on_progress(step: str, detail: str) -> None:
            self.store.update(job_id, step=step, detail=detail)

        try:
            final_path = generate_story(job.story_path, on_progress=on_progress)
        except Exception as exc:  # frontière du worker : toute erreur doit être capturée et exposée via l'API
            self.store.update(
                job_id,
                status=JobStatus.FAILED,
                error=str(exc),
                detail=traceback.format_exc(limit=3),
            )
            return

        self.store.update(job_id, status=JobStatus.COMPLETED, result_path=str(final_path))
