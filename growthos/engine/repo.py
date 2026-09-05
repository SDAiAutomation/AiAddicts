"""DB access for the content pipeline (content_items, content_performance).

Runs through the service_role client on purpose: this CLI is executed
directly by the account owner, there is no signed-in Supabase Auth session
to scope an anon/RLS client to. See engine/db.py for the anon-vs-service
distinction.
"""
from datetime import datetime, timedelta, timezone

# Un item resté en 'generating' plus longtemps qu'un run normal (mesuré :
# 30-90s pour un script de quelques blocs) n'a plus de worker vivant derrière
# — kill, crash, coupure réseau. 15 min laisse une marge large (le job
# GitHub Actions a lui-même un timeout de 12 min) avant de le remettre en
# file, tout en le récupérant dans un délai raisonnable.
_STALE_GENERATING_MINUTES = 15


def get_or_create_organization(client, name: str) -> str:
    # `organizations.name` has no unique constraint on purpose (two real tenants
    # can share a workspace name), so this stays a select-then-insert rather than
    # an upsert. Fine for the single-user dogfooding CLI running sequentially.
    existing = client.table("organizations").select("id").eq("name", name).limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]
    created = client.table("organizations").insert({"name": name}).execute()
    return created.data[0]["id"]


def get_or_create_account(client, organization_id: str, platform: str, handle: str, niche: str | None = None) -> str:
    # Idempotent on the accounts (organization_id, platform, handle) unique
    # constraint. `niche` is only sent when set, so re-running a script that
    # omits it never wipes an existing value.
    payload = {"organization_id": organization_id, "platform": platform, "handle": handle}
    if niche:
        payload["niche"] = niche
    row = (
        client.table("accounts")
        .upsert(payload, on_conflict="organization_id,platform,handle")
        .execute()
    )
    return row.data[0]["id"]


def create_content_item(client, account_id: str, title: str, status: str, script: dict, video_url: str | None = None) -> str:
    payload = {"account_id": account_id, "title": title, "status": status, "script": script}
    if video_url:
        payload["video_url"] = video_url
    created = client.table("content_items").insert(payload).execute()
    return created.data[0]["id"]


def get_script(client, content_item_id: str) -> dict:
    row = (
        client.table("content_items").select("script").eq("id", content_item_id).single().execute()
    )
    script = row.data["script"]
    if not script:
        raise ValueError(f"content_item {content_item_id} n'a pas de script (rien à générer)")
    return script


def reclaim_stale_generating_items(client) -> int:
    """Remet en 'queued' tout item bloqué en 'generating' depuis plus de
    `_STALE_GENERATING_MINUTES` — un worker mort en plein travail (kill,
    crash, coupure) laisse sinon la ligne orpheline pour toujours, puisque
    claim_queued_item() ne regarde que 'queued'. Appelé à chaque poll, avant
    de réclamer le prochain job. Retourne le nombre d'items récupérés."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=_STALE_GENERATING_MINUTES)).isoformat()
    reclaimed = (
        client.table("content_items")
        .update({"status": "queued", "generation_step": None, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("status", "generating")
        .lt("updated_at", cutoff)
        .execute()
    )
    return len(reclaimed.data)


def claim_queued_item(client) -> dict | None:
    """Réclame le plus ancien content_item en file (status='queued') pour un
    worker : le fait passer à 'generating' avec un update conditionné au
    statut encore 'queued', pour rester correct si deux workers tournent en
    parallèle (le second, arrivé après, ne récupère aucune ligne). Retourne
    la ligne réclamée ({id, script}) ou None si la file est vide."""
    reclaimed = reclaim_stale_generating_items(client)
    if reclaimed:
        print(f"       {reclaimed} item(s) 'generating' orphelin(s) remis en file")

    queued = (
        client.table("content_items")
        .select("id, script")
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .execute()
    )
    if not queued.data:
        return None

    item = queued.data[0]
    claimed = (
        client.table("content_items")
        .update({"status": "generating", "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", item["id"])
        .eq("status", "queued")
        .execute()
    )
    if not claimed.data:
        return None  # un autre worker l'a pris entre-temps
    return item


def update_content_item(client, content_item_id: str, **fields) -> None:
    fields.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    client.table("content_items").update(fields).eq("id", content_item_id).execute()


def mark_failed(client, content_item_id: str, error: str) -> None:
    # Colonne `error` en text, pas de limite stricte côté DB, mais on borne
    # quand même — pas la peine de stocker une trace complète en base.
    client.table("content_items").update(
        {
            "status": "failed",
            "error": error[:2000],
            "generation_step": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", content_item_id).execute()


def charge_generation_credit(client, content_item_id: str) -> None:
    """Décompte 1 crédit (= 1 vidéo, cf. page Tarifs growthos-web) sur
    l'organisation propriétaire de ce content_item, à appeler une fois la
    génération réussie. Business (plan sur devis) n'a pas de limite, donc
    rien à décompter. Journalisé dans credits_ledger comme toute variation
    de solde (le webhook Stripe y écrit aussi, pour les recharges).

    Best-effort côté appelant : ne doit jamais faire échouer un run par
    ailleurs réussi, voir le wrapping dans assembler.run_for_content_item.
    """
    item = (
        client.table("content_items")
        .select("accounts(organization_id)")
        .eq("id", content_item_id)
        .single()
        .execute()
    )
    organization_id = item.data["accounts"]["organization_id"]

    org = (
        client.table("organizations")
        .select("plan, credits_balance")
        .eq("id", organization_id)
        .single()
        .execute()
    ).data
    if org["plan"] == "business":
        return  # illimité par design, pas de décompte

    new_balance = max(0, org["credits_balance"] - 1)
    client.table("organizations").update({"credits_balance": new_balance}).eq(
        "id", organization_id
    ).execute()
    client.table("credits_ledger").insert(
        {
            "organization_id": organization_id,
            "delta": new_balance - org["credits_balance"],
            "reason": "video_generated",
            "related_content_item_id": content_item_id,
            "balance_after": new_balance,
        }
    ).execute()


def mark_published(client, content_item_id: str) -> None:
    client.table("content_items").update({
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", content_item_id).execute()


def log_performance(client, content_item_id: str, **metrics) -> str:
    payload = {"content_item_id": content_item_id, **{k: v for k, v in metrics.items() if v is not None}}
    created = client.table("content_performance").insert(payload).execute()
    return created.data[0]["id"]
