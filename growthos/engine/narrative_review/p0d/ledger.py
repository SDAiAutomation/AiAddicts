"""Journal financier DURABLE d'une campagne P0-D : un fichier SQLite local, transactionnel, sans service supplémentaire.

Une campagne = un fichier. Le journal est à la fois :
- la SOURCE DE VÉRITÉ des réservations et des montants (la comptabilité en mémoire n'en est qu'un miroir) ;
- le VERROU de la campagne : au plus UNE tentative non résolue (`reserved`, `sending`, `unreconciled`) à tout instant, vérifié dans la transaction qui crée la suivante ;
- l'état de BLOCAGE de la campagne (`halted_reason`), qui survit au redémarrage.

Machine d'états d'une tentative (chaque transition est une transaction validée sur disque, `synchronous=FULL`) :

    reserved ──> sending ──> settled            coût connu, dans la réservation
       │            └──────> unreconciled ──> reconciled     coût inconnu : bloque la campagne jusqu'à réconciliation explicite
       └─────────────────────> released         PROUVÉ non envoyé (seul état libérable)

- `reserved` est écrit AVANT tout envoi (durable). `sending` est écrit juste AVANT l'appel de l'émetteur : si le processus meurt, aucune trace ne permet de dire si l'émission a eu lieu.
- Au redémarrage (`recover`) : `reserved` -> `released` (le marqueur `sending` précède toujours l'émission : il est prouvé que rien n'est parti) ; `sending` -> `unreconciled` et la campagne est
  BLOQUÉE (issue incertaine). Rien ne la débloque sauf `reconcile` explicite puis `clear_halt` explicite.
- Un seul processus propriétaire par campagne (verrou de fichier du système, relâché par l'OS à la mort du processus) ; dans un processus, toutes les instances partagent le même verrou
  de section critique : plusieurs exécuteurs sur la même campagne ne contournent rien.

LIMITES : la garantie vaut pour des processus qui passent par ce module. Elle ne protège pas d'un processus qui écrit directement dans le fichier SQLite, de la suppression du fichier, ni de la perte
du disque. Un système de fichiers qui ignore `fsync` affaiblit la durabilité. Les montants sont des estimations, pas des factures.
"""
from __future__ import annotations

import contextlib
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import contract as c

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - plateforme POSIX
    import fcntl

UNRESOLVED = ("reserved", "sending", "unreconciled")
EMITTED = ("sending", "settled", "unreconciled", "reconciled")    # états atteints seulement après (ou pendant) une émission possible
SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign(
  id TEXT PRIMARY KEY, ceiling_usd REAL NOT NULL, max_calls INTEGER NOT NULL, halted_reason TEXT, halted_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempt(
  label TEXT PRIMARY KEY, seq INTEGER NOT NULL UNIQUE, max_usd REAL NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('reserved','sending','settled','unreconciled','reconciled','released')),
  actual_usd REAL, note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS event(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, label TEXT, kind TEXT NOT NULL, detail TEXT);
"""


class LedgerError(c.ReviewError):
    def __init__(self, message: str):
        super().__init__(c.BUDGET_EXHAUSTED, message)


class _Owner:
    def __init__(self, handle):
        self.handle, self.refs, self.lock, self.fresh = handle, 0, threading.RLock(), True


_registry_lock = threading.Lock()
_owners: dict[str, _Owner] = {}


def _os_lock(handle) -> None:
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:  # pragma: no cover
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _positive_finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


class CampaignLedger:
    def __init__(self, path, *, campaign_id: str, ceiling_usd: float, max_calls: int, clock: Callable[[], datetime] | None = None):
        if not (isinstance(campaign_id, str) and campaign_id.strip() and _positive_finite(ceiling_usd) and isinstance(max_calls, int) and not isinstance(max_calls, bool) and max_calls > 0):
            raise LedgerError("a ledger needs a campaign id, a positive finite ceiling and a positive call cap")
        self.path, self.campaign_id, self.ceiling_usd, self.max_calls = Path(path), campaign_id, float(ceiling_usd), max_calls
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.recovered: list[tuple[str, str]] = []     # (étiquette, ancien état) des tentatives résolues au redémarrage
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key = os.path.realpath(self.path)
        self._owner = self._acquire()
        try:
            self._init_schema()
            if self._owner.fresh:                  # premier propriétaire de CE processus : tout état non terminal appartient à un processus mort
                self.recovered = self._recover()
                self._owner.fresh = False
        except BaseException:
            self.close()
            raise

    # --- propriété et section critique ---------------------------------------------------------------------------------------------------------

    def _acquire(self) -> _Owner:
        with _registry_lock:
            owner = _owners.get(self._key)
            if owner is None:
                handle = open(self._key + ".owner", "a+b")
                try:
                    handle.write(b"x")
                    handle.flush()
                    _os_lock(handle)
                except OSError as exc:
                    handle.close()
                    raise LedgerError("this campaign ledger is owned by another live process: refused") from exc
                owner = _owners[self._key] = _Owner(handle)
            owner.refs += 1
            return owner

    def critical_section(self):
        """Verrou de la campagne, PARTAGÉ par toutes les instances de ce processus : la transaction complète d'une tentative s'y déroule (une seule en vol)."""
        return self._owner.lock

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with _registry_lock:
            self._owner.refs -= 1
            if self._owner.refs == 0:
                _owners.pop(self._key, None)
                self._owner.handle.close()            # relâche le verrou de fichier

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- base ------------------------------------------------------------------------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextlib.contextmanager
    def _tx(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def _fault(self, point: str) -> None:
        """Point d'injection de panne pour les tests (sans effet ici)."""

    def _now(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    def _event(self, conn, kind: str, label: str | None = None, detail: str | None = None) -> None:
        conn.execute("INSERT INTO event(at, label, kind, detail) VALUES (?,?,?,?)", (self._now(), label, kind, detail))

    def _init_schema(self) -> None:
        with self._tx() as conn:
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)
            row = conn.execute("SELECT ceiling_usd, max_calls FROM campaign WHERE id=?", (self.campaign_id,)).fetchone()
            if row is None:
                if conn.execute("SELECT COUNT(*) FROM campaign").fetchone()[0]:
                    raise LedgerError("this ledger file belongs to another campaign")
                conn.execute("INSERT INTO campaign(id, ceiling_usd, max_calls, created_at) VALUES (?,?,?,?)", (self.campaign_id, self.ceiling_usd, self.max_calls, self._now()))
                self._event(conn, "campaign_created")
            elif (row[0], row[1]) != (self.ceiling_usd, self.max_calls):
                raise LedgerError("the ledger was created with another ceiling or call cap: refused")

    def _recover(self) -> list[tuple[str, str]]:
        done = []
        with self._tx() as conn:
            for label, state in conn.execute("SELECT label, state FROM attempt WHERE state IN ('reserved','sending')").fetchall():
                if state == "reserved":
                    conn.execute("UPDATE attempt SET state='released', note='restart: marker `sending` was never written, nothing was sent', updated_at=? WHERE label=?", (self._now(), label))
                else:
                    conn.execute("UPDATE attempt SET state='unreconciled', note='restart: outcome uncertain (process died while sending)', updated_at=? WHERE label=?", (self._now(), label))
                    conn.execute("UPDATE campaign SET halted_reason=COALESCE(halted_reason, 'RECOVERED_UNCERTAIN_ATTEMPT'), halted_at=COALESCE(halted_at, ?) WHERE id=?",
                                 (self._now(), self.campaign_id))
                self._event(conn, "recovered", label, state)
                done.append((label, state))
        return done

    # --- transitions -----------------------------------------------------------------------------------------------------------------------------

    def begin_attempt(self, label: str, max_usd: float) -> int:
        """Réservation DURABLE, avant tout envoi. Refuse : campagne bloquée, tentative non résolue, plafond d'appels ou plafond monétaire dépassé, étiquette déjà utilisée."""
        if not (isinstance(label, str) and label.strip()) or not _positive_finite(max_usd):
            raise LedgerError("an attempt needs a unique label and a positive finite maximum cost")
        with self._tx() as conn:
            halted = conn.execute("SELECT halted_reason FROM campaign WHERE id=?", (self.campaign_id,)).fetchone()[0]
            if halted:
                raise LedgerError(f"campaign halted ({halted}): no new attempt")
            pending = conn.execute(f"SELECT label, state FROM attempt WHERE state IN ({','.join('?' * len(UNRESOLVED))})", UNRESOLVED).fetchall()
            if pending:
                raise LedgerError(f"unresolved attempt {pending[0][0]!r} ({pending[0][1]}): no new attempt before it is resolved")
            if conn.execute("SELECT 1 FROM attempt WHERE label=?", (label,)).fetchone():
                raise LedgerError("an attempt label can never be reused")
            emitted = conn.execute(f"SELECT COUNT(*) FROM attempt WHERE state IN ({','.join('?' * len(EMITTED))})", EMITTED).fetchone()[0]
            if emitted >= self.max_calls:
                raise LedgerError("the authorised number of provider calls is exhausted (durable count)")
            committed = self._committed(conn)
            if committed + max_usd > self.ceiling_usd + 1e-12:
                raise LedgerError(f"{max_usd:.6f} USD would exceed the ceiling (durable total {committed:.6f})")
            seq = (conn.execute("SELECT COALESCE(MAX(seq), 0) FROM attempt").fetchone()[0]) + 1
            now = self._now()
            conn.execute("INSERT INTO attempt(label, seq, max_usd, state, created_at, updated_at) VALUES (?,?,?,?,?,?)", (label, seq, max_usd, "reserved", now, now))
            self._event(conn, "reserved", label, f"max_usd={max_usd}")
            self._fault("begin_before_commit")
        return seq

    @staticmethod
    def _committed(conn) -> float:
        known = conn.execute("SELECT COALESCE(SUM(actual_usd), 0) FROM attempt WHERE state IN ('settled','reconciled')").fetchone()[0]
        held = conn.execute("SELECT COALESCE(SUM(max_usd), 0) FROM attempt WHERE state IN ('reserved','sending','unreconciled')").fetchone()[0]
        return known + held

    def _move(self, conn, label: str, allowed: tuple, new: str, *, actual: float | None = None, note: str | None = None) -> None:
        row = conn.execute("SELECT state FROM attempt WHERE label=?", (label,)).fetchone()
        if row is None:
            raise LedgerError(f"unknown attempt {label!r}")
        if row[0] not in allowed:
            raise LedgerError(f"attempt {label!r} is {row[0]!r}: cannot go to {new!r} (allowed from {allowed})")
        conn.execute("UPDATE attempt SET state=?, actual_usd=COALESCE(?, actual_usd), note=COALESCE(?, note), updated_at=? WHERE label=?", (new, actual, note, self._now(), label))
        self._event(conn, new, label, note)

    def mark_sending(self, label: str) -> None:
        """Écrit durablement `sending` JUSTE AVANT l'appel de l'émetteur. Si cette écriture échoue, l'émission n'a pas lieu."""
        with self._tx() as conn:
            self._move(conn, label, ("reserved",), "sending")
            self._fault("mark_sending_before_commit")

    def release(self, label: str, note: str = "proved not sent") -> None:
        """Libère une réservation : possible UNIQUEMENT depuis `reserved` (aucun marqueur d'émission écrit)."""
        with self._tx() as conn:
            self._move(conn, label, ("reserved",), "released", note=note)

    def settle(self, label: str, actual_usd: float) -> None:
        if not (isinstance(actual_usd, (int, float)) and not isinstance(actual_usd, bool) and math.isfinite(actual_usd) and actual_usd >= 0):
            raise LedgerError("a settled cost must be finite and non-negative; an unknown cost goes through mark_unreconciled")
        with self._tx() as conn:
            self._move(conn, label, ("sending",), "settled", actual=float(actual_usd))

    def mark_unreconciled(self, label: str, reason: str) -> None:
        """Issue d'un envoi dont le coût n'est pas établi : montant maximal conservé, campagne BLOQUÉE (durablement)."""
        with self._tx() as conn:
            self._move(conn, label, ("sending",), "unreconciled", note=reason)
            conn.execute("UPDATE campaign SET halted_reason=COALESCE(halted_reason, ?), halted_at=COALESCE(halted_at, ?) WHERE id=?", (reason, self._now(), self.campaign_id))

    def halt(self, reason: str) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE campaign SET halted_reason=COALESCE(halted_reason, ?), halted_at=COALESCE(halted_at, ?) WHERE id=?", (reason, self._now(), self.campaign_id))
            self._event(conn, "halt", None, reason)

    def reconcile(self, label: str, actual_usd: float, note: str) -> None:
        """Réconciliation EXPLICITE d'une tentative `unreconciled` (montant lu par le propriétaire). Transaction unique : tout ou rien. Ne débloque PAS la campagne."""
        if not (isinstance(actual_usd, (int, float)) and not isinstance(actual_usd, bool) and math.isfinite(actual_usd) and actual_usd >= 0) or not (isinstance(note, str) and note.strip()):
            raise LedgerError("a reconciliation needs a finite non-negative amount and a non-empty note")
        with self._tx() as conn:
            self._move(conn, label, ("unreconciled",), "reconciled", actual=float(actual_usd), note=note)
            self._fault("reconcile_before_commit")

    def clear_halt(self, note: str) -> None:
        """Déblocage EXPLICITE de la campagne : seulement quand plus aucune tentative n'est non résolue."""
        if not (isinstance(note, str) and note.strip()):
            raise LedgerError("clearing a halt needs a note")
        with self._tx() as conn:
            pending = conn.execute(f"SELECT label FROM attempt WHERE state IN ({','.join('?' * len(UNRESOLVED))})", UNRESOLVED).fetchall()
            if pending:
                raise LedgerError(f"unresolved attempt(s) {[p[0] for p in pending]}: reconcile them first")
            conn.execute("UPDATE campaign SET halted_reason=NULL, halted_at=NULL WHERE id=?", (self.campaign_id,))
            self._event(conn, "halt_cleared", None, note)

    # --- lecture ---------------------------------------------------------------------------------------------------------------------------------

    def halted(self) -> str | None:
        with contextlib.closing(self._connect()) as conn:
            return conn.execute("SELECT halted_reason FROM campaign WHERE id=?", (self.campaign_id,)).fetchone()[0]

    def unresolved(self) -> list[str]:
        with contextlib.closing(self._connect()) as conn:
            return [r[0] for r in conn.execute(f"SELECT label FROM attempt WHERE state IN ({','.join('?' * len(UNRESOLVED))}) ORDER BY seq", UNRESOLVED)]

    def state_of(self, label: str) -> str | None:
        with contextlib.closing(self._connect()) as conn:
            row = conn.execute("SELECT state FROM attempt WHERE label=?", (label,)).fetchone()
            return row[0] if row else None

    def attempts(self) -> list[dict]:
        with contextlib.closing(self._connect()) as conn:
            cols = ("label", "seq", "max_usd", "state", "actual_usd", "note", "created_at", "updated_at")
            return [dict(zip(cols, r)) for r in conn.execute(f"SELECT {','.join(cols)} FROM attempt ORDER BY seq")]

    def events(self) -> list[tuple]:
        with contextlib.closing(self._connect()) as conn:
            return conn.execute("SELECT at, label, kind, detail FROM event ORDER BY id").fetchall()

    def snapshot(self) -> dict:
        with contextlib.closing(self._connect()) as conn:
            settled = conn.execute("SELECT COALESCE(SUM(actual_usd), 0) FROM attempt WHERE state IN ('settled','reconciled')").fetchone()[0]
            unreconciled = {r[0]: r[1] for r in conn.execute("SELECT label, max_usd FROM attempt WHERE state='unreconciled'")}
            return {"settled_usd": settled, "unreconciled": unreconciled, "committed_usd": self._committed(conn), "halted": self.halted(),
                    "emitted": conn.execute(f"SELECT COUNT(*) FROM attempt WHERE state IN ({','.join('?' * len(EMITTED))})", EMITTED).fetchone()[0]}
