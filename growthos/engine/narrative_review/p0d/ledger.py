"""Journal financier DURABLE d'une campagne P0-D : un fichier SQLite local, transactionnel, sans service supplémentaire.

IDENTITÉ ET RACINE DE CONFIANCE
- Une campagne a UN SEUL journal canonique. Son chemin n'est jamais choisi par l'exécuteur : il est DÉRIVÉ de la racine de confiance déclarée dans l'autorisation approuvée
  (`ledger_root`) et de l'identifiant de campagne : `<racine>/campaigns/<sha256(campaign_id)[:32]>/ledger.sqlite` (`ledger_path`).
- La RACINE DE CONFIANCE est un répertoire administré par le propriétaire (écriture réservée au compte qui exécute la campagne) ET l'autorisation approuvée. Le journal porte, dans sa table `meta`,
  l'identifiant de campagne, l'empreinte du CŒUR de l'autorisation et un nonce aléatoire généré à l'initialisation. L'autorisation porte `ledger_binding_sha256` = SHA-256(campagne, cœur, nonce) : un journal
  absent, remplacé, copié ailleurs, réinitialisé ou issu d'une autre autorisation ne peut PAS reproduire cette empreinte (le nonce n'existe que dans le journal d'origine). Un fichier marqueur à côté du
  journal ne serait pas une preuve (les deux peuvent être recréés ensemble) : l'ancre est dans l'autorisation, hors du répertoire.
- Création : UNIQUEMENT par `LedgerStore.initialize`, étape explicite du propriétaire, qui refuse tout répertoire de campagne déjà présent. `LedgerStore.open` n'en crée jamais : journal absent = refus,
  sans envoi.
- Politique de récupération : un journal perdu, remplacé ou réinitialisé N'EST PAS reconstruit. Il faut un NOUVEL identifiant de campagne et une NOUVELLE autorisation ; les dépenses de l'ancienne
  campagne se reconstituent à la main depuis les factures du fournisseur. Chaque transaction revérifie l'identité du journal (un fichier remplacé en cours de route fait échouer l'opération).
- Chemins : la racine doit être absolue et déjà canonique (ni lien symbolique, ni jonction, ni nom court, ni `..`), le fichier ne doit pas être un lien et n'avoir qu'un lien physique ; la clé de
  verrouillage est le chemin réel normalisé (casse comprise sous Windows).
- LIMITE : si le répertoire de confiance n'est pas administré (n'importe qui peut y écrire ou en restaurer une ancienne copie), l'unicité et la non-régression ne peuvent pas être garanties. Une copie
  ANCIENNE du journal d'origine (retour en arrière) porte le bon nonce et n'est pas détectable sans ancre externe : le répertoire doit être protégé, et le propriétaire consigne l'état final.

CYCLE DE VIE : après `close()` toute opération échoue. `close()` attend la fin d'une tentative en cours dans un autre thread (même verrou de campagne) et refuse de fermer depuis l'intérieur d'une tentative ;
le verrou de fichier du système n'est relâché que par la dernière fermeture, sous ce verrou.

TRANSACTIONS : chaque transition est une transaction validée sur disque. Le règlement et la décision de blocage d'un dépassement sont inscrits DANS LA MÊME transaction.

Machine d'états d'une tentative :

    reserved ──> sending ──> settled            coût connu (bloque si dépassement de la réservation ou raison d'arrêt)
       │            └──────> unreconciled ──> reconciled     coût inconnu : bloque la campagne jusqu'à réconciliation explicite
       └─────────────────────> released         PROUVÉ non envoyé (seul état libérable)

Au redémarrage (`recover`) : `reserved` -> `released` (le marqueur `sending` précède toujours l'émission) ; `sending` -> `unreconciled` et campagne BLOQUÉE ; tout règlement en dépassement non bloqué est bloqué.

LIMITES : la garantie vaut pour des processus qui passent par ce module. Elle ne protège pas d'un processus qui écrit directement dans le fichier, de la suppression de la racine entière, ni de la perte du disque.
Un système de fichiers qui ignore `fsync` affaiblit la durabilité. Les montants sont des estimations, pas des factures.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

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
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
BINDING_FIELD = "ledger_binding_sha256"


class LedgerError(c.ReviewError):
    def __init__(self, message: str):
        super().__init__(c.BUDGET_EXHAUSTED, message)


# --- identité canonique ------------------------------------------------------------------------------------------------------------------------

def _norm(path) -> str:
    return os.path.normcase(os.path.realpath(path))


def canonical_root_problems(root) -> list[str]:
    """Problèmes d'une racine de confiance : absolue, existante, répertoire, DÉJÀ canonique (aucun lien symbolique, jonction, nom court ou `..` : l'alias est refusé, pas résolu)."""
    if not isinstance(root, str) or not root.strip():
        return ["ledger_root must be a non-empty text"]
    out = []
    if not os.path.isabs(root):
        out.append("ledger_root must be an absolute path")
    elif os.path.normpath(root) != root:
        out.append("ledger_root must be written in normalized form (no '.', '..', repeated or trailing separators)")
    elif os.path.normcase(os.path.abspath(root)) != _norm(root):
        out.append("ledger_root must already be canonical (no symbolic link, junction, short name or '..'): an alias is refused, not resolved")
    elif not os.path.isdir(root):
        out.append("ledger_root must be an existing directory")
    return out


def ledger_path(root, campaign_id: str) -> Path:
    """Le SEUL chemin autorisé du journal d'une campagne : dérivé, jamais choisi par l'exécuteur."""
    return Path(root) / "campaigns" / hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()[:32] / "ledger.sqlite"


def core_digest(raw: Mapping) -> str:
    """Empreinte du CŒUR de l'autorisation : tout sauf l'empreinte de liaison du journal (qu'elle contient par construction)."""
    core = {k: v for k, v in dict(raw).items() if k != BINDING_FIELD}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=list).encode("utf-8")).hexdigest()


def binding_for(campaign_id: str, core_sha: str, nonce: str) -> str:
    return hashlib.sha256(json.dumps({"campaign_id": campaign_id, "core": core_sha, "nonce": nonce}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


# --- propriété (verrou de campagne) ------------------------------------------------------------------------------------------------------------

class _Owner:
    def __init__(self, handle):
        self.handle, self.refs, self.lock, self.fresh = handle, 0, threading.RLock(), True
        self.local = threading.local()

    def depth(self) -> int:
        return getattr(self.local, "depth", 0)


class _Section:
    """Section critique de la campagne : verrou de campagne + profondeur par thread (pour refuser une fermeture depuis l'intérieur d'une tentative)."""

    def __init__(self, ledger: "CampaignLedger"):
        self._ledger = ledger

    def __enter__(self):
        self._ledger._ensure_open()
        owner = self._ledger._owner
        owner.lock.acquire()
        try:
            self._ledger._ensure_open()            # fermé pendant l'attente : refus
        except BaseException:
            owner.lock.release()
            raise
        owner.local.depth = owner.depth() + 1
        return self

    def __exit__(self, *exc):
        owner = self._ledger._owner
        owner.local.depth = owner.depth() - 1
        owner.lock.release()


_registry_lock = threading.Lock()
_owners: dict[str, _Owner] = {}


def _os_lock(handle) -> None:
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:  # pragma: no cover
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _positive_finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


# --- le journal --------------------------------------------------------------------------------------------------------------------------------

class CampaignLedger:
    """Mode `legacy` (tests unitaires) : crée le fichier au besoin, sans identité liée. Les modes `initialize` et `bound` ne sont atteints que par `LedgerStore`."""

    def __init__(self, path, *, campaign_id: str, ceiling_usd: float, max_calls: int, clock: Callable[[], datetime] | None = None,
                 _mode: str = "legacy", _core: str | None = None, _nonce: str | None = None, _binding: str | None = None):
        if not (isinstance(campaign_id, str) and campaign_id.strip() and _positive_finite(ceiling_usd) and isinstance(max_calls, int) and not isinstance(max_calls, bool) and max_calls > 0):
            raise LedgerError("a ledger needs a campaign id, a positive finite ceiling and a positive call cap")
        self.path, self.campaign_id, self.ceiling_usd, self.max_calls = Path(path), campaign_id, float(ceiling_usd), max_calls
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.recovered: list[tuple[str, str]] = []     # (étiquette, ancien état) des tentatives résolues au redémarrage
        self.binding: str | None = None                # empreinte de liaison (journaux issus de LedgerStore seulement)
        self._bound_core: str | None = None
        self._closed = True                            # tant que la construction n'est pas terminée
        if _mode == "bound" and not self.path.is_file():
            raise LedgerError("the canonical ledger does not exist: it is never created implicitly (initialize it first; a lost ledger needs a new campaign id and a new authorization)")
        if _mode != "legacy":
            self._check_file_identity()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key = _norm(self.path)
        self._owner = self._acquire()
        self._closed = False
        try:
            if _mode == "bound":
                self.binding, self._bound_core = _binding, _core
            self._init_schema(_mode, _core, _nonce, _binding)
            if self._owner.fresh:                  # premier propriétaire de CE processus : tout état non terminal appartient à un processus mort
                self.recovered = self._recover()
                self._owner.fresh = False
        except BaseException:
            self._force_close()
            raise

    # --- chemin et fichier ---------------------------------------------------------------------------------------------------------------------

    def _check_file_identity(self) -> None:
        """Pas de lien symbolique ni de jonction sur le chemin, un seul lien physique : deux noms pour un même journal contourneraient la clé de verrouillage."""
        if os.path.normcase(os.path.abspath(self.path)) != _norm(self.path):
            raise LedgerError("the ledger path is an alias (symbolic link, junction, short name or '..'): refused")
        if self.path.exists() and os.stat(self.path).st_nlink != 1:
            raise LedgerError("the ledger file has several hard links: refused")

    # --- propriété et section critique ---------------------------------------------------------------------------------------------------------

    def _acquire(self) -> _Owner:
        with _registry_lock:
            owner = _owners.get(self._key)
            if owner is None:
                handle = open(str(self.path) + ".owner", "a+b")
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

    def _ensure_open(self) -> None:
        if self._closed:
            raise LedgerError("the ledger is closed: every operation is refused")

    def critical_section(self):
        """Verrou de la campagne, PARTAGÉ par toutes les instances de ce processus : la transaction complète d'une tentative s'y déroule (une seule en vol)."""
        self._ensure_open()
        return _Section(self)

    def _release_owner(self) -> None:
        with _registry_lock:
            self._owner.refs -= 1
            if self._owner.refs == 0:
                _owners.pop(self._key, None)
                self._owner.handle.close()            # relâche le verrou de fichier : seulement à la DERNIÈRE fermeture

    def _force_close(self) -> None:
        if getattr(self, "_owner", None) is not None and not self._closed:
            self._closed = True
            self._release_owner()
        self._closed = True

    def close(self, timeout: float = 30.0) -> None:
        """Ferme le journal. Attend la fin d'une tentative en cours dans un AUTRE thread (même verrou de campagne) ; refuse depuis l'intérieur d'une tentative."""
        if self._closed:
            return
        if self._owner.depth() > 0:
            raise LedgerError("cannot close the ledger from inside an active attempt")
        if not self._owner.lock.acquire(timeout=timeout):
            raise LedgerError("an attempt is still in flight: the ledger was not closed")
        try:
            if not self._closed:
                self._closed = True
                self._release_owner()
        finally:
            self._owner.lock.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- base ------------------------------------------------------------------------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self._ensure_open()
        if self.binding is not None and not self.path.is_file():
            raise LedgerError("the canonical ledger file vanished: refused (never recreated)")
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _verify_identity(self, conn) -> None:
        """Journal lié : l'identité écrite dans le fichier doit être celle de l'autorisation, à CHAQUE transaction et lecture (un fichier remplacé en cours de route est détecté)."""
        if self.binding is None:
            return
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall()) if conn.execute("SELECT name FROM sqlite_master WHERE name='meta'").fetchone() else {}
        expected = binding_for(meta.get("campaign_id", ""), meta.get("core_digest", ""), meta.get("nonce", "")) if meta else None
        if not meta or expected != self.binding or meta.get("campaign_id") != self.campaign_id or meta.get("core_digest") != self._bound_core:
            raise LedgerError("the ledger on disk is not the one bound to this authorization (replaced, reset or from another campaign): refused")

    @contextlib.contextmanager
    def _conn(self):
        conn = self._connect()
        try:
            self._verify_identity(conn)
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def _tx(self, name: str):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                self._verify_identity(conn)
                yield conn
                self._fault(f"before_commit:{name}")
                conn.execute("COMMIT")
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        self._fault(f"after_commit:{name}")

    def _fault(self, point: str) -> None:
        """Point d'injection de panne pour les tests (sans effet ici)."""

    def _now(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    def _event(self, conn, kind: str, label: str | None = None, detail: str | None = None) -> None:
        conn.execute("INSERT INTO event(at, label, kind, detail) VALUES (?,?,?,?)", (self._now(), label, kind, detail))

    def _init_schema(self, mode: str, core: str | None, nonce: str | None, binding: str | None) -> None:
        with self._tx("init") as conn:
            if mode == "bound":
                if not conn.execute("SELECT name FROM sqlite_master WHERE name='meta'").fetchone():
                    raise LedgerError("this file is not a bound campaign ledger: refused")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)
            if mode == "initialize":
                conn.executemany("INSERT INTO meta(key, value) VALUES (?,?)", [("campaign_id", self.campaign_id), ("core_digest", core), ("nonce", nonce), ("schema", "2")])
                self.binding, self._bound_core = binding_for(self.campaign_id, core, nonce), core
            self._verify_identity(conn)
            row = conn.execute("SELECT ceiling_usd, max_calls FROM campaign WHERE id=?", (self.campaign_id,)).fetchone()
            if row is None:
                if mode == "bound":
                    raise LedgerError("the bound ledger has no campaign row: refused")
                if conn.execute("SELECT COUNT(*) FROM campaign").fetchone()[0]:
                    raise LedgerError("this ledger file belongs to another campaign")
                conn.execute("INSERT INTO campaign(id, ceiling_usd, max_calls, created_at) VALUES (?,?,?,?)", (self.campaign_id, self.ceiling_usd, self.max_calls, self._now()))
                self._event(conn, "campaign_created")
            elif (row[0], row[1]) != (self.ceiling_usd, self.max_calls):
                raise LedgerError("the ledger was created with another ceiling or call cap: refused")

    def _recover(self) -> list[tuple[str, str]]:
        done = []
        with self._tx("recover") as conn:
            for label, state in conn.execute("SELECT label, state FROM attempt WHERE state IN ('reserved','sending')").fetchall():
                if state == "reserved":
                    conn.execute("UPDATE attempt SET state='released', note='restart: marker `sending` was never written, nothing was sent', updated_at=? WHERE label=?", (self._now(), label))
                else:
                    conn.execute("UPDATE attempt SET state='unreconciled', note='restart: outcome uncertain (process died while sending)', updated_at=? WHERE label=?", (self._now(), label))
                    conn.execute("UPDATE campaign SET halted_reason=COALESCE(halted_reason, 'RECOVERED_UNCERTAIN_ATTEMPT'), halted_at=COALESCE(halted_at, ?) WHERE id=?",
                                 (self._now(), self.campaign_id))
                self._event(conn, "recovered", label, state)
                done.append((label, state))
            if conn.execute("SELECT 1 FROM attempt WHERE state IN ('settled','reconciled') AND actual_usd > max_usd + 1e-12 LIMIT 1").fetchone():   # filet : un dépassement ne reste jamais débloqué
                conn.execute("UPDATE campaign SET halted_reason=COALESCE(halted_reason, 'COST_EXCEEDED_RESERVATION'), halted_at=COALESCE(halted_at, ?) WHERE id=?", (self._now(), self.campaign_id))
        return done

    # --- transitions -----------------------------------------------------------------------------------------------------------------------------

    def begin_attempt(self, label: str, max_usd: float) -> int:
        """Réservation DURABLE, avant tout envoi. Refuse : campagne bloquée, tentative non résolue, plafond d'appels ou plafond monétaire dépassé, étiquette déjà utilisée."""
        if not (isinstance(label, str) and label.strip()) or not _positive_finite(max_usd):
            raise LedgerError("an attempt needs a unique label and a positive finite maximum cost")
        with self._tx("begin") as conn:
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
        return seq

    @staticmethod
    def _committed(conn) -> float:
        known = conn.execute("SELECT COALESCE(SUM(actual_usd), 0) FROM attempt WHERE state IN ('settled','reconciled')").fetchone()[0]
        held = conn.execute("SELECT COALESCE(SUM(max_usd), 0) FROM attempt WHERE state IN ('reserved','sending','unreconciled')").fetchone()[0]
        return known + held

    def _move(self, conn, label: str, allowed: tuple, new: str, *, actual: float | None = None, note: str | None = None) -> float:
        row = conn.execute("SELECT state, max_usd FROM attempt WHERE label=?", (label,)).fetchone()
        if row is None:
            raise LedgerError(f"unknown attempt {label!r}")
        if row[0] not in allowed:
            raise LedgerError(f"attempt {label!r} is {row[0]!r}: cannot go to {new!r} (allowed from {allowed})")
        conn.execute("UPDATE attempt SET state=?, actual_usd=COALESCE(?, actual_usd), note=COALESCE(?, note), updated_at=? WHERE label=?", (new, actual, note, self._now(), label))
        self._event(conn, new, label, note)
        return row[1]

    def _halt_in(self, conn, reason: str) -> None:
        conn.execute("UPDATE campaign SET halted_reason=COALESCE(halted_reason, ?), halted_at=COALESCE(halted_at, ?) WHERE id=?", (reason, self._now(), self.campaign_id))
        self._event(conn, "halt", None, reason)

    def mark_sending(self, label: str) -> None:
        """Écrit durablement `sending` JUSTE AVANT l'appel de l'émetteur. Si cette écriture échoue, l'émission n'a pas lieu."""
        with self._tx("mark_sending") as conn:
            self._move(conn, label, ("reserved",), "sending")

    def release(self, label: str, note: str = "proved not sent") -> None:
        """Libère une réservation : possible UNIQUEMENT depuis `reserved` (aucun marqueur d'émission écrit)."""
        with self._tx("release") as conn:
            self._move(conn, label, ("reserved",), "released", note=note)

    def settle(self, label: str, actual_usd: float, halt_reason: str | None = None) -> bool:
        """Règlement d'un coût CONNU. Le règlement ET la décision de blocage (dépassement de la réservation, ou `halt_reason` fourni par l'appelant) sont inscrits dans UNE SEULE
        transaction : aucun crash ne peut laisser un dépassement réglé et non bloqué. Retourne vrai si le coût dépasse la réservation."""
        if not (isinstance(actual_usd, (int, float)) and not isinstance(actual_usd, bool) and math.isfinite(actual_usd) and actual_usd >= 0):
            raise LedgerError("a settled cost must be finite and non-negative; an unknown cost goes through mark_unreconciled")
        with self._tx("settle") as conn:
            reserved = self._move(conn, label, ("sending",), "settled", actual=float(actual_usd))
            overrun = actual_usd > reserved + 1e-12
            reason = "COST_EXCEEDED_RESERVATION" if overrun else halt_reason
            if reason:
                self._halt_in(conn, reason)
        return overrun

    def mark_unreconciled(self, label: str, reason: str) -> None:
        """Issue d'un envoi dont le coût n'est pas établi : montant maximal conservé, campagne BLOQUÉE dans la même transaction."""
        with self._tx("mark_unreconciled") as conn:
            self._move(conn, label, ("sending",), "unreconciled", note=reason)
            self._halt_in(conn, reason)

    def halt(self, reason: str) -> None:
        with self._tx("halt") as conn:
            self._halt_in(conn, reason)

    def reconcile(self, label: str, actual_usd: float, note: str) -> None:
        """Réconciliation EXPLICITE d'une tentative `unreconciled` (montant lu par le propriétaire). Transaction unique : tout ou rien. Ne débloque PAS la campagne."""
        if not (isinstance(actual_usd, (int, float)) and not isinstance(actual_usd, bool) and math.isfinite(actual_usd) and actual_usd >= 0) or not (isinstance(note, str) and note.strip()):
            raise LedgerError("a reconciliation needs a finite non-negative amount and a non-empty note")
        with self._tx("reconcile") as conn:
            reserved = self._move(conn, label, ("unreconciled",), "reconciled", actual=float(actual_usd), note=note)
            if actual_usd > reserved + 1e-12:
                self._halt_in(conn, "COST_EXCEEDED_RESERVATION")

    def clear_halt(self, note: str) -> None:
        """Déblocage EXPLICITE de la campagne : seulement quand plus aucune tentative n'est non résolue."""
        if not (isinstance(note, str) and note.strip()):
            raise LedgerError("clearing a halt needs a note")
        with self._tx("clear_halt") as conn:
            pending = conn.execute(f"SELECT label FROM attempt WHERE state IN ({','.join('?' * len(UNRESOLVED))})", UNRESOLVED).fetchall()
            if pending:
                raise LedgerError(f"unresolved attempt(s) {[p[0] for p in pending]}: reconcile them first")
            conn.execute("UPDATE campaign SET halted_reason=NULL, halted_at=NULL WHERE id=?", (self.campaign_id,))
            self._event(conn, "halt_cleared", None, note)

    # --- lecture ---------------------------------------------------------------------------------------------------------------------------------

    def halted(self) -> str | None:
        with self._conn() as conn:
            return conn.execute("SELECT halted_reason FROM campaign WHERE id=?", (self.campaign_id,)).fetchone()[0]

    def unresolved(self) -> list[str]:
        with self._conn() as conn:
            return [r[0] for r in conn.execute(f"SELECT label FROM attempt WHERE state IN ({','.join('?' * len(UNRESOLVED))}) ORDER BY seq", UNRESOLVED)]

    def state_of(self, label: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT state FROM attempt WHERE label=?", (label,)).fetchone()
            return row[0] if row else None

    def attempts(self) -> list[dict]:
        with self._conn() as conn:
            cols = ("label", "seq", "max_usd", "state", "actual_usd", "note", "created_at", "updated_at")
            return [dict(zip(cols, r)) for r in conn.execute(f"SELECT {','.join(cols)} FROM attempt ORDER BY seq")]

    def events(self) -> list[tuple]:
        with self._conn() as conn:
            return conn.execute("SELECT at, label, kind, detail FROM event ORDER BY id").fetchall()

    def snapshot(self) -> dict:
        with self._conn() as conn:
            settled = conn.execute("SELECT COALESCE(SUM(actual_usd), 0) FROM attempt WHERE state IN ('settled','reconciled')").fetchone()[0]
            unreconciled = {r[0]: r[1] for r in conn.execute("SELECT label, max_usd FROM attempt WHERE state='unreconciled'")}
            return {"settled_usd": settled, "unreconciled": unreconciled, "committed_usd": self._committed(conn),
                    "halted": conn.execute("SELECT halted_reason FROM campaign WHERE id=?", (self.campaign_id,)).fetchone()[0],
                    "emitted": conn.execute(f"SELECT COUNT(*) FROM attempt WHERE state IN ({','.join('?' * len(EMITTED))})", EMITTED).fetchone()[0]}


# --- magasin de journaux canoniques -------------------------------------------------------------------------------------------------------------

class LedgerStore:
    """Le SEUL moyen d'obtenir un journal de campagne pour un exécuteur : racine de confiance déclarée par l'autorisation, chemin dérivé, identité liée, aucune création implicite."""

    def __init__(self, root):
        problems = canonical_root_problems(str(root))
        if problems:
            raise LedgerError("untrusted ledger root: " + "; ".join(problems))
        self.root = str(root)

    def path_for(self, campaign_id: str) -> Path:
        return ledger_path(self.root, campaign_id)

    def initialize(self, core: Mapping, *, clock: Callable[[], datetime] | None = None) -> str:
        """Étape EXPLICITE du propriétaire, avant l'approbation : crée le journal d'une NOUVELLE campagne et retourne `ledger_binding_sha256` à inscrire dans l'autorisation.
        `core` = l'autorisation complète SANS `ledger_binding_sha256`. Refuse tout répertoire de campagne déjà présent (pas de réinitialisation : un journal perdu exige une nouvelle campagne)."""
        core = dict(core)
        if BINDING_FIELD in core:
            raise LedgerError("initialize takes the authorization WITHOUT its binding field")
        cid = core.get("campaign_id")
        if not isinstance(cid, str) or not cid.strip() or _norm(core.get("ledger_root", "")) != _norm(self.root):
            raise LedgerError("the authorization names another ledger root or no campaign id")
        path = self.path_for(cid)
        if path.parent.exists():
            raise LedgerError("this campaign is already initialized in the trusted root: re-initialization is refused (a lost or reset ledger needs a NEW campaign id and a NEW authorization)")
        path.parent.mkdir(parents=True)
        nonce, digest = secrets.token_hex(32), core_digest(core)
        ledger = CampaignLedger(path, campaign_id=cid, ceiling_usd=core["ceiling_usd"], max_calls=core["max_logical_calls"], clock=clock, _mode="initialize", _core=digest, _nonce=nonce)
        try:
            return ledger.binding
        finally:
            ledger.close()

    def open(self, auth_raw: Mapping, *, ledger_cls=CampaignLedger, clock: Callable[[], datetime] | None = None) -> CampaignLedger:
        """Ouvre le journal canonique de l'autorisation, sans jamais le créer. Absent, remplacé, réinitialisé, copié ailleurs ou lié à une autre autorisation : refus (aucun envoi possible)."""
        raw = dict(auth_raw)
        cid, binding = raw.get("campaign_id"), raw.get(BINDING_FIELD)
        if _norm(raw.get("ledger_root", "")) != _norm(self.root):
            raise LedgerError("the authorization names another ledger root than this store's")
        if not isinstance(cid, str) or not isinstance(binding, str) or not re.fullmatch(r"[0-9a-f]{64}", binding):
            raise LedgerError("the authorization has no valid ledger binding")
        return ledger_cls(self.path_for(cid), campaign_id=cid, ceiling_usd=raw["ceiling_usd"], max_calls=raw["max_logical_calls"], clock=clock, _mode="bound",
                          _core=core_digest(raw), _binding=binding)
