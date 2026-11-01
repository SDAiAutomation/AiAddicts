"""Durable, cumulative spend ledger of ONE illustrated episode, shared by all its runs, retries and regenerations.

Why: the per-run `BudgetTracker` is in memory and the runner is ephemeral, so a resumed job started again from zero and the episode
ceiling only held per execution. The ledger makes the ceiling cumulative.

Storage: the EXISTING table `content_assets` (service role only, one row per paid call), no migration. Rows use kind `image` (the table's
CHECK allows voice / voice_words / image only) and an `input_hash` that starts with `LEDGER_PREFIX`, so they can never be mistaken for an
asset (asset keys are 32 hex characters). `estimated_cost` carries the amount, `provider` the state and the item.

Concurrency: every reservation APPENDS the row `LEDGER_PREFIX + <next sequence number>`. The table's `unique (content_item_id, kind,
input_hash)` makes two workers that read the same total insert the same sequence number: one wins, the other gets a unique violation, re-reads
the new total and decides again. That is an optimistic, linearizable check-and-reserve built on a constraint that already exists.

Fail-closed everywhere: an unreadable ledger, an unknown or invalid amount, a conflict that does not resolve, or a total above the ceiling REFUSES
the paid call. A call whose outcome is uncertain (timeout, exception, unknown cost) keeps its reservation and is never counted as free.
"""
from __future__ import annotations

import math
import re
import threading

from .cost import BudgetExceeded

TABLE = "content_assets"
KIND = "image"  # the table only accepts voice / voice_words / image
LEDGER_PREFIX = "story-visual-ledger-"
_SEQ = re.compile(re.escape(LEDGER_PREFIX) + r"(\d{1,9})$")
MAX_ROWS = 900  # PostgREST returns at most 1000 rows: beyond this the total could be silently truncated, so refuse
RETRIES = 8
RESERVED, SETTLED, UNCERTAIN = "reserved", "settled", "uncertain"


class LedgerUnavailable(BudgetExceeded):
    """The durable spend cannot be read or written: no paid call is allowed."""


def _amount(value) -> float:
    if isinstance(value, bool) or value is None:
        raise LedgerUnavailable("ledger row without a valid amount")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LedgerUnavailable("ledger row with an unreadable amount") from exc
    if not math.isfinite(number) or number < 0:
        raise LedgerUnavailable("ledger row with an invalid amount")
    return number


def _is_conflict(exc: Exception) -> bool:
    return str(getattr(exc, "code", "")) == "23505" or "duplicate key" in str(exc).lower() or "23505" in str(exc)


class DurableLedger:
    def __init__(self, client, content_item_id: str, cap_usd: float, retries: int = RETRIES):
        if not content_item_id or isinstance(cap_usd, bool) or not isinstance(cap_usd, (int, float)) or not math.isfinite(cap_usd) or cap_usd < 0:
            raise ValueError("ledger needs a content item and a finite, non-negative ceiling")
        self.client, self.content_item_id, self.cap_usd, self.retries = client, content_item_id, float(cap_usd), retries
        self._open: dict[str, str] = {}  # item -> input_hash of its open reservation
        self._lock = threading.Lock()

    # ---- reading -------------------------------------------------------------------------------------------------------------------
    def _rows(self) -> list[dict]:
        try:
            rows = (self.client.table(TABLE).select("input_hash, estimated_cost, provider").eq("content_item_id", self.content_item_id)
                    .eq("kind", KIND).like("input_hash", LEDGER_PREFIX + "%").execute().data)
        except Exception as exc:  # noqa: BLE001 - unreadable durable state: refuse
            raise LedgerUnavailable(f"spend ledger unreadable ({type(exc).__name__})") from exc
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise LedgerUnavailable("spend ledger unreadable or too large")
        return rows

    def _state(self) -> tuple[float, int]:
        total, last = 0.0, 0
        for row in self._rows():
            match = _SEQ.match(str(row.get("input_hash", "")))
            if not match:
                raise LedgerUnavailable("ledger row with an unexpected key")
            total += _amount(row.get("estimated_cost"))
            last = max(last, int(match.group(1)))
        return round(total, 6), last

    def total(self) -> float:
        """Cumulative spend of the episode (every run, retry and regeneration). Raises `LedgerUnavailable` if it cannot be read."""
        return self._state()[0]

    def remaining(self) -> float:
        return round(self.cap_usd - self.total(), 6)

    # ---- reserving, settling ---------------------------------------------------------------------------------------------------------
    def reserve(self, item: str, expected_usd: float | None) -> None:
        """Append a reservation BEFORE a paid call. Refuses an unknown amount, an unreadable ledger or a total above the ceiling."""
        if expected_usd is None or isinstance(expected_usd, bool) or not isinstance(expected_usd, (int, float)) or not math.isfinite(expected_usd) or expected_usd < 0:
            raise BudgetExceeded(f"{item}: cost unknown or invalid, refusing a paid call")
        for _ in range(self.retries):
            total, last = self._state()
            if total + expected_usd > self.cap_usd + 1e-9:
                raise BudgetExceeded(f"{item}: ${total + expected_usd:.2f} cumulative would exceed the ${self.cap_usd:.2f} episode ceiling")
            key = f"{LEDGER_PREFIX}{last + 1:06d}"
            try:
                self.client.table(TABLE).insert({"content_item_id": self.content_item_id, "kind": KIND, "input_hash": key, "storage_path": "",
                                                 "bytes": 0, "estimated_cost": round(float(expected_usd), 6),
                                                 "provider": f"ledger:{RESERVED}:{item}"[:120]}).execute()
            except Exception as exc:  # noqa: BLE001
                if _is_conflict(exc):
                    continue  # another worker appended first: re-read the new total and decide again
                raise LedgerUnavailable(f"spend ledger not writable ({type(exc).__name__})") from exc
            with self._lock:
                self._open[item] = key
            return
        raise LedgerUnavailable("spend ledger busy: could not reserve, refusing the paid call")

    def settle(self, item: str, actual_usd: float | None) -> None:
        """After the call. A MEASURED cost replaces the reservation (releasing the unused part); an unknown cost (None) keeps the reservation
        and marks it uncertain: a timeout or an unknown price is never counted as free. Never raises: on failure the reservation simply stays."""
        with self._lock:
            key = self._open.pop(item, None)
        if key is None:
            return
        if actual_usd is None or isinstance(actual_usd, bool) or not math.isfinite(actual_usd) or actual_usd < 0:
            values = {"provider": f"ledger:{UNCERTAIN}:{item}"[:120]}
        else:
            values = {"estimated_cost": round(float(actual_usd), 6), "provider": f"ledger:{SETTLED}:{item}"[:120]}
        try:
            self.client.table(TABLE).update(values).eq("content_item_id", self.content_item_id).eq("kind", KIND).eq("input_hash", key).execute()
        except Exception as exc:  # noqa: BLE001 - the reservation stays: conservative
            print(f"       (dépense non soldée dans le registre : {type(exc).__name__} ; la retenue est conservée)")

    def release(self, item: str) -> None:
        """Cancel a reservation whose call was DEFINITELY not made. Anything uncertain must go through `settle(item, None)` instead."""
        with self._lock:
            key = self._open.pop(item, None)
        if key is None:
            return
        try:
            self.client.table(TABLE).update({"estimated_cost": 0, "provider": f"ledger:released:{item}"[:120]}).eq("content_item_id", self.content_item_id) \
                .eq("kind", KIND).eq("input_hash", key).execute()
        except Exception as exc:  # noqa: BLE001
            print(f"       (retenue non libérée : {type(exc).__name__} ; conservée)")
