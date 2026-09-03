"""Rattacher un utilisateur Supabase Auth aux organisations créées par la CLI.

Contexte : `main.py` et `log_metrics.py` écrivent via le client `service_role`,
qui contourne RLS. Ils créent des lignes `organizations` et `accounts`, mais
jamais de `profiles` ni de `organization_members`. Or toutes les policies RLS
passent par `internal.current_user_org_ids()`, qui lit `organization_members`
pour `auth.uid()`. Résultat : un utilisateur fraîchement connecté ne verrait
rien. Ce script crée les lignes `profiles` + `organization_members` manquantes.

`content_items` / `content_performance` n'ont PAS besoin d'une colonne
`organization_id` : leur RLS résout l'organisation via
`account_id -> accounts.organization_id`.

À lancer une fois que l'utilisateur existe réellement dans Supabase Auth
(inscription via l'app ou le dashboard).

Usage :
    python scripts/backfill_membership.py --list
    python scripts/backfill_membership.py --email moi@example.com --dry-run
    python scripts/backfill_membership.py --email moi@example.com
    python scripts/backfill_membership.py --email moi@example.com --org "GrowthOS Dogfooding" --role owner
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from engine import db

VALID_ROLES = ("owner", "strategist", "editor", "client_viewer")
_PAGE = 200


def auth_user_by_email(client, email: str):
    """Trouve un utilisateur Supabase Auth par email (service_role, paginé)."""
    target = email.strip().lower()
    page = 1
    while True:
        users = client.auth.admin.list_users(page=page, per_page=_PAGE)
        for u in users:
            if (u.email or "").lower() == target:
                return u
        if len(users) < _PAGE:
            return None
        page += 1


def print_state(client) -> None:
    orgs = client.table("organizations").select("id,name").execute().data
    members = client.table("organization_members").select("organization_id,user_id,role").execute().data
    by_org: dict[str, list] = {}
    for m in members:
        by_org.setdefault(m["organization_id"], []).append(m)

    print(f"{len(orgs)} organisation(s) :")
    for o in orgs:
        ms = by_org.get(o["id"], [])
        tag = "   <-- ORPHELINE (aucun membre)" if not ms else ""
        print(f"  {o['id']}  {o['name']!r}  membres={len(ms)}{tag}")
        for m in ms:
            print(f"      {m['role']:<14} {m['user_id']}")

    users = client.auth.admin.list_users(page=1, per_page=_PAGE)
    print(f"\n{len(users)} utilisateur(s) Auth :")
    for u in users:
        print(f"  {u.id}  {u.email}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--email", help="email de l'utilisateur Supabase Auth à rattacher")
    parser.add_argument("--org", help="nom exact d'une organisation à cibler (défaut : toutes les orphelines)")
    parser.add_argument("--role", default="owner", choices=VALID_ROLES)
    parser.add_argument("--list", action="store_true", help="afficher l'état (orgs, membres, users) et quitter")
    parser.add_argument("--dry-run", action="store_true", help="montrer ce qui serait écrit, sans rien écrire")
    args = parser.parse_args()

    client = db.get_service_client()

    if args.list:
        print_state(client)
        return

    if not args.email:
        parser.error("--email est requis (ou utilise --list)")

    user = auth_user_by_email(client, args.email)
    if user is None:
        sys.exit(
            f"Aucun utilisateur Supabase Auth avec l'email {args.email!r}.\n"
            "Inscris-toi d'abord (app, ou dashboard Supabase → Authentication → Add user), puis relance."
        )
    uid = user.id
    meta = user.user_metadata or {}
    full_name = meta.get("full_name") or meta.get("name")
    print(f"Utilisateur Auth : {uid}  ({args.email})")

    orgs = client.table("organizations").select("id,name").execute().data
    if args.org:
        targets = [o for o in orgs if o["name"] == args.org]
        if not targets:
            sys.exit(f"Aucune organisation nommée {args.org!r}.")
    else:
        members = client.table("organization_members").select("organization_id").execute().data
        with_members = {m["organization_id"] for m in members}
        targets = [o for o in orgs if o["id"] not in with_members]
        if not targets:
            print("Aucune organisation orpheline — rien à faire.")
            return
    print("Organisation(s) ciblée(s) : " + ", ".join(repr(o["name"]) for o in targets))

    # profiles
    has_profile = client.table("profiles").select("id").eq("id", uid).limit(1).execute().data
    if has_profile:
        print("profiles : ligne déjà présente")
    elif args.dry_run:
        print(f"profiles : CRÉERAIT {{id: {uid}, email: {args.email}, full_name: {full_name!r}}}")
    else:
        client.table("profiles").insert(
            {"id": uid, "email": args.email, "full_name": full_name}
        ).execute()
        print("profiles : ligne créée")

    # organization_members
    for o in targets:
        existing = (
            client.table("organization_members")
            .select("role")
            .eq("organization_id", o["id"])
            .eq("user_id", uid)
            .limit(1)
            .execute()
            .data
        )
        if existing:
            print(f"  {o['name']!r} : déjà membre (role={existing[0]['role']})")
        elif args.dry_run:
            print(f"  {o['name']!r} : AJOUTERAIT un membre role={args.role}")
        else:
            client.table("organization_members").insert(
                {"organization_id": o["id"], "user_id": uid, "role": args.role}
            ).execute()
            print(f"  {o['name']!r} : membre ajouté (role={args.role})")

    if args.dry_run:
        print("\n(dry-run — rien écrit)")


if __name__ == "__main__":
    main()
