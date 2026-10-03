"""Événements produit (lot L5, audit bible 2026-10-03).

Un événement par moment utile à la mesure « coût par vidéo satisfaisante » :
démarrage / fin / échec d'un run de génération, avec son coût. Le rapport de
coût stocké sur le content_item est écrasé à chaque run ; ces lignes gardent
le coût de CHAQUE essai.

Jamais bloquant : une erreur d'écriture est journalisée et ignorée, la
génération n'en dépend pas.
"""


def organization_id_of(client, content_item_id: str) -> str | None:
    try:
        row = (
            client.table("content_items")
            .select("accounts(organization_id)")
            .eq("id", content_item_id)
            .single()
            .execute()
        )
        return (row.data.get("accounts") or {}).get("organization_id")
    except Exception as exc:
        print(f"       (organisation introuvable pour l'événement : {exc})")
        return None


def record(client, event: str, content_item_id: str, organization_id: str | None, **props) -> None:
    """Écrit un événement. Sans organisation connue, ne fait rien."""
    if not organization_id:
        return
    try:
        client.table("product_events").insert({
            "organization_id": organization_id,
            "content_item_id": content_item_id,
            "event": event,
            "props": {k: v for k, v in props.items() if v is not None},
        }).execute()
    except Exception as exc:
        print(f"       (événement {event} non enregistré : {exc})")
