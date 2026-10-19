"""Accès à l'Explainer (bêta admin) vérifié PAR LE WORKER, juste avant la réservation du crédit.

Pourquoi ici : le site masque le style et refuse un non-admin (growthos-web), mais un utilisateur connecté peut écrire
`content_items.script` et passer `status` à `queued` directement par l'API (voir la migration
`guard_content_items_internal_columns`) ; et les épisodes de série sont mis en file par `queue_due_series_episodes`
sans passer par le site. Le worker rend ce que dit `script.visual_style` : c'est lui qui doit refuser.

Règle (échec fermé, jamais de repli vers un autre style) : le contenu est rendu seulement si son AUTEUR est dans
`ADMIN_USER_IDS` (mêmes identifiants Supabase que le site).
- auteur = `content_items.requested_by` s'il existe (la base impose `requested_by = auth.uid()` aux écritures clientes,
  donc un utilisateur ne peut pas se faire passer pour un admin) ;
- sinon, pour un épisode de série, `series.created_by` (rempli et protégé par la migration `series_created_by`) ;
- sinon : refusé.
"""
from __future__ import annotations

import os
import re

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class ExplainerAccessDenied(PermissionError):
    """Le contenu demande l'Explainer sans que son auteur soit administrateur."""


def parse_admin_ids(raw: str | None) -> set[str]:
    """Même lecture que `isAdminUserId` côté site : UUID séparés par virgules, points-virgules ou espaces ; tout le reste
    (dont un e-mail, modifiable et usurpable) est ignoré."""
    ids = set()
    for part in re.split(r"[\s,;]+", str(raw or "")):
        candidate = part.strip().lower()
        if UUID.fullmatch(candidate):
            ids.add(candidate)
    return ids


def _first(client, table: str, columns: str, key: str, value: str) -> dict | None:
    rows = client.table(table).select(columns).eq(key, value).limit(1).execute().data
    return rows[0] if rows else None


def authorize(client, content_item_id: str, admin_ids_raw: str | None = None) -> str:
    """Renvoie l'identifiant de l'auteur admin, ou lève `ExplainerAccessDenied` avec le motif (écrit au journal du worker)."""
    admins = parse_admin_ids(admin_ids_raw if admin_ids_raw is not None else os.environ.get("ADMIN_USER_IDS"))
    if not admins:
        raise ExplainerAccessDenied("Explainer refusé : ADMIN_USER_IDS est absent ou vide sur le worker")
    item = _first(client, "content_items", "requested_by, series_id", "id", content_item_id) or {}
    author = item.get("requested_by")
    if not author and item.get("series_id"):
        try:
            series = _first(client, "series", "created_by", "id", item["series_id"]) or {}
        except Exception as exc:  # noqa: BLE001 — colonne absente (migration non appliquée) ou lecture impossible : on refuse
            raise ExplainerAccessDenied(f"Explainer refusé : auteur de la série illisible ({type(exc).__name__}) ; migration series_created_by appliquée ?") from exc
        author = series.get("created_by")
    if not author:
        raise ExplainerAccessDenied("Explainer refusé : auteur du contenu inconnu (ni requested_by ni série créée par un administrateur)")
    if str(author).lower() not in admins:
        raise ExplainerAccessDenied("Explainer refusé : réservé aux administrateurs de la plateforme")
    return str(author).lower()
