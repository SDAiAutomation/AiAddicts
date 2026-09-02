"""Weekly metrics log — the 6 KPI from the dogfooding plan, nothing more.

One row per account per week. Kept as a flat CSV on purpose: this is week
1-2 tooling, not the Analytics screen from the product design system.
"""
import csv
from pathlib import Path

FIELDS = [
    "date", "compte", "video_id", "titre",
    "publications_semaine", "vues_moyennes", "watch_time_pct",
    "abonnes_nets", "engagement", "leads", "notes",
]


def ensure_csv(path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        with p.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()
    return path


def append_row(path: str, row: dict) -> None:
    ensure_csv(path)
    missing = set(row) - set(FIELDS)
    if missing:
        raise ValueError(f"champs inconnus dans la ligne de métriques : {sorted(missing)}")
    with Path(path).open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow({field: row.get(field, "") for field in FIELDS})


def read_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
