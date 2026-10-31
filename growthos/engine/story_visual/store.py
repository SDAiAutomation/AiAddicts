"""Écritures atomiques, manifestes fiables et verrou de job (un seul exécuteur payant par histoire).

Un manifeste illisible n'est JAMAIS traité comme vide (cela repayerait toutes les scènes) : on lève `ManifestCorrupt`.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from pathlib import Path

LOCK_STALE_S = 3600.0
_held = threading.local()


class ManifestCorrupt(RuntimeError):
    pass


class JobBusy(RuntimeError):
    """Une autre exécution payante est en cours sur cette histoire."""


def atomic_write(path: Path, data: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestCorrupt(f"{path.name} is unreadable; refusing to regenerate paid assets blindly") from exc
    if not isinstance(data, dict):
        raise ManifestCorrupt(f"{path.name} is malformed")
    return data


def save_manifest(path: Path, manifest: dict) -> None:
    atomic_write(path, json.dumps(manifest, indent=2, sort_keys=True))


@contextlib.contextmanager
def job_lock(folder: Path):
    """Verrou par dossier d'histoire, réentrant dans un même thread ; verrou périmé (> 1 h) récupéré."""
    held = getattr(_held, "paths", None)
    if held is None:
        held = _held.paths = set()
    lock = Path(folder) / "job.lock"
    if lock in held:
        yield
        return
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE_S:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            raise JobBusy("another run is already generating this story")
    else:
        raise JobBusy("could not acquire the job lock")
    held.add(lock)
    try:
        yield
    finally:
        held.discard(lock)
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()
