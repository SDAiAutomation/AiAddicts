"""DB access for the content pipeline (content_items, content_performance).

Runs through the service_role client on purpose: this CLI is executed
directly by the account owner, there is no signed-in Supabase Auth session
to scope an anon/RLS client to. See engine/db.py for the anon-vs-service
distinction.
"""
from datetime import datetime, timezone


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


def mark_published(client, content_item_id: str) -> None:
    client.table("content_items").update({
        "status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", content_item_id).execute()


def log_performance(client, content_item_id: str, **metrics) -> str:
    payload = {"content_item_id": content_item_id, **{k: v for k, v in metrics.items() if v is not None}}
    created = client.table("content_performance").insert(payload).execute()
    return created.data[0]["id"]
