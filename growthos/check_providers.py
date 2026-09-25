"""Contrôle de santé des fournisseurs et de la file de génération.

Lancé toutes les heures par `.github/workflows/growthos-health.yml`, qui
ouvre un ticket GitHub (donc un e-mail) quand un problème apparaît et le
ferme quand tout est revenu à la normale. Né d'un incident réel : le crédit
prépayé OpenAI s'est épuisé le 2026-09-25 et on ne l'a découvert que par
hasard, trois heures plus tard.

Vérifie :
- OpenAI : clé valide et crédit disponible (un appel minimal) ;
- ElevenLabs : clé valide et caractères restants sur l'abonnement ;
- connexions YouTube / TikTok expirées ou révoquées ;
- générations échouées récemment et file bloquée ;
- montages AutoEdit bloqués (en file ou en traitement) ou en échec technique.

Le dépôt est PUBLIC : ticket et logs sont visibles de tous, donc aucun
secret, titre de vidéo ni message d'erreur brut dans le rapport.

Écrit `health-report.md` (corps du ticket) et `health-signature.txt`
(liste stable des problèmes : le ticket n'est mis à jour que si elle
change). Code de sortie toujours 0 : c'est le ticket qui alerte.

Usage:
    python check_providers.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests
from dotenv import load_dotenv

load_dotenv()

from engine import db

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ELEVENLABS_SUBSCRIPTION_URL = "https://api.elevenlabs.io/v1/user/subscription"
ELEVENLABS_VOICES_URL = "https://api.elevenlabs.io/v1/voices"

# Une vidéo consomme ~1 000 caractères de voix (mesuré le 2026-09-25).
_DEFAULT_ELEVENLABS_MIN_CHARS = 10_000
FAILED_WINDOW = timedelta(hours=2)
# Le worker passe toutes les 10 min : 45 min en file = il ne tourne plus.
QUEUED_STUCK_AFTER = timedelta(minutes=45)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def check_openai() -> tuple[list[tuple[str, str]], list[str]]:
    """(problèmes, notes). Un 429 de limite de débit ou un 5xx est
    passager : pas d'alerte, seul un crédit épuisé ou une clé refusée compte."""
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("HEALTH_OPENAI_MODEL", "").strip()
    if not api_key:
        return [("openai:no_key", "OpenAI : `OPENAI_API_KEY` absente.")], []
    if not model:
        return [], ["OpenAI non vérifié : `HEALTH_OPENAI_MODEL` non configuré."]
    try:
        resp = requests.post(
            OPENAI_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": [{"role": "user", "content": "ok"}]},
            timeout=60,
        )
    except requests.RequestException as exc:
        return [], [f"OpenAI injoignable pendant le contrôle ({exc.__class__.__name__}), à revérifier."]
    if resp.ok:
        return [], []
    try:
        code = (resp.json().get("error") or {}).get("code") or ""
    except ValueError:
        code = ""
    if resp.status_code == 401:
        return [("openai:auth", "OpenAI : clé API refusée (401). Vérifier `OPENAI_API_KEY`.")], []
    if resp.status_code == 429 and (code in {"insufficient_quota", "credit_balance_exhausted"} or "quota" in code):
        return [(
            "openai:credit",
            "OpenAI : **crédit prépayé épuisé** — scripts, images et contrôle d'originalité sont bloqués. "
            "Recharger sur platform.openai.com → Billing (le budget mensuel n'est pas le solde).",
        )], []
    return [], [f"OpenAI a répondu {resp.status_code} {code} pendant le contrôle (passager ?)."]


def check_elevenlabs() -> tuple[list[tuple[str, str]], list[str]]:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return [("elevenlabs:no_key", "ElevenLabs : `ELEVENLABS_API_KEY` absente.")], []
    headers = {"xi-api-key": api_key}
    try:
        resp = requests.get(ELEVENLABS_SUBSCRIPTION_URL, headers=headers, timeout=30)
        if resp.status_code == 401:
            # Une clé restreinte peut ne pas avoir le droit de lire
            # l'abonnement : on vérifie au moins qu'elle est acceptée.
            voices = requests.get(ELEVENLABS_VOICES_URL, headers=headers, timeout=30)
            if voices.status_code == 401:
                return [("elevenlabs:auth", "ElevenLabs : clé API refusée (401). Vérifier `ELEVENLABS_API_KEY`.")], []
            return [], ["ElevenLabs : clé valide, mais sans droit de lecture de l'abonnement (quota non vérifié)."]
    except requests.RequestException as exc:
        return [], [f"ElevenLabs injoignable pendant le contrôle ({exc.__class__.__name__}), à revérifier."]
    if not resp.ok:
        return [], [f"ElevenLabs a répondu {resp.status_code} pendant le contrôle (passager ?)."]
    sub = resp.json()
    limit = int(sub.get("character_limit") or 0)
    used = int(sub.get("character_count") or 0)
    remaining = limit - used
    minimum = _int_env("ELEVENLABS_MIN_CHARS", _DEFAULT_ELEVENLABS_MIN_CHARS)
    status = str(sub.get("status") or "")
    problems = []
    if status and status not in {"active", "trialing", "free"}:
        problems.append(("elevenlabs:status", f"ElevenLabs : abonnement au statut « {status} »."))
    if limit and remaining < minimum:
        problems.append((
            "elevenlabs:credit",
            f"ElevenLabs : **plus que {max(remaining, 0):,} caractères** sur {limit:,} "
            f"(~{max(remaining, 0) // 1000} vidéo(s)) — la voix off va s'arrêter.",
        ))
    return problems, [f"ElevenLabs : {max(remaining, 0):,} caractères restants sur {limit:,}."]


def check_connections(client) -> list[tuple[str, str]]:
    rows = (
        client.table("account_oauth_tokens")
        .select("account_id,platform,status,accounts(handle)")
        .neq("status", "connected")
        .execute()
        .data or []
    )
    problems = []
    for row in sorted(rows, key=lambda r: (r["platform"], r["account_id"])):
        handle = (row.get("accounts") or {}).get("handle") or row["account_id"][:8]
        problems.append((
            f"oauth:{row['platform']}:{row['account_id']}",
            f"{row['platform'].capitalize()} : connexion **{row['status']}** pour le compte « {handle} » "
            "— publication et relevé des métriques bloqués. Reconnecter depuis sa page Comptes.",
        ))
    return problems


def check_queue(client, now: datetime) -> list[tuple[str, str]]:
    problems = []
    failed = (
        client.table("content_items")
        .select("id")
        .eq("status", "failed")
        .gte("updated_at", (now - FAILED_WINDOW).isoformat())
        .execute()
        .data or []
    )
    if failed:
        # Le dépôt est public : pas de titre ni de message d'erreur dans le
        # ticket, le détail se lit dans l'app (onglet Contenu).
        problems.append((
            "queue:failed",
            f"Génération : **{len(failed)} vidéo(s) en échec** depuis {int(FAILED_WINDOW.total_seconds() // 3600)} h "
            "— voir le message d'erreur sur la vidéo dans l'app.",
        ))
    stuck = (
        client.table("content_items")
        .select("id")
        .eq("status", "queued")
        .lte("updated_at", (now - QUEUED_STUCK_AFTER).isoformat())
        .execute()
        .data or []
    )
    if stuck:
        problems.append((
            "queue:stuck",
            f"Génération : **{len(stuck)} vidéo(s) en file depuis plus de "
            f"{int(QUEUED_STUCK_AFTER.total_seconds() // 60)} min** — le worker GitHub ne tourne peut-être plus.",
        ))
    return problems


# Échecs dus à l'utilisateur (crédits, envoi abandonné, fichier absent) : pas
# une panne de notre côté, donc pas d'alerte.
_AUTOEDIT_USER_ERRORS = ("insufficient_credits", "upload_incomplete", "source_missing")
# Un job réclamé est remis en file au bout de 15 min sans worker vivant.
AUTOEDIT_RUNNING_STUCK_AFTER = timedelta(minutes=30)


def check_autoedit(client, now: datetime) -> list[tuple[str, str]]:
    """Montages AutoEdit bloqués en file, bloqués en cours de traitement ou en
    échec technique récent (ajouté le 2026-09-25 : un montage est resté 2 h
    en file sans qu'aucune alerte ne parte)."""
    problems = []
    queued = (
        client.table("autoedit_jobs").select("id").eq("status", "queued")
        .lte("updated_at", (now - QUEUED_STUCK_AFTER).isoformat()).execute().data or []
    )
    if queued:
        problems.append((
            "autoedit:stuck",
            f"AutoEdit : **{len(queued)} montage(s) en file depuis plus de "
            f"{int(QUEUED_STUCK_AFTER.total_seconds() // 60)} min** — le worker GitHub ne tourne peut-être plus.",
        ))
    running = (
        client.table("autoedit_jobs").select("id").in_("status", ["analyzing", "planning", "rendering"])
        .lte("updated_at", (now - AUTOEDIT_RUNNING_STUCK_AFTER).isoformat()).execute().data or []
    )
    if running:
        problems.append((
            "autoedit:running_stuck",
            f"AutoEdit : **{len(running)} montage(s) bloqué(s) en traitement** depuis plus de "
            f"{int(AUTOEDIT_RUNNING_STUCK_AFTER.total_seconds() // 60)} min.",
        ))
    failed = (
        client.table("autoedit_jobs").select("id,error").eq("status", "failed")
        .gte("updated_at", (now - FAILED_WINDOW).isoformat()).execute().data or []
    )
    technical = [r for r in failed if ((r.get("error") or {}).get("code")) not in _AUTOEDIT_USER_ERRORS]
    if technical:
        codes = sorted({str((r.get("error") or {}).get("code") or "?") for r in technical})
        problems.append((
            "autoedit:failed",
            f"AutoEdit : **{len(technical)} montage(s) en échec technique** depuis "
            f"{int(FAILED_WINDOW.total_seconds() // 3600)} h (codes : {', '.join(codes)}).",
        ))
    return problems


def build_report(problems: list[tuple[str, str]], notes: list[str], now: datetime) -> str:
    lines = [f"Contrôle du {now:%Y-%m-%d %H:%M} UTC.", ""]
    if problems:
        lines += ["**Problèmes :**", ""] + [f"- {text}" for _, text in problems]
    else:
        lines.append("Aucun problème.")
    if notes:
        lines += ["", "Notes :", ""] + [f"- {note}" for note in notes]
    return "\n".join(lines) + "\n"


def main() -> int:
    now = datetime.now(timezone.utc)
    problems: list[tuple[str, str]] = []
    notes: list[str] = []

    for check in (check_openai, check_elevenlabs):
        found, info = check()
        problems += found
        notes += info
    try:
        client = db.get_service_client()
        problems += check_connections(client)
        problems += check_queue(client, now)
        problems += check_autoedit(client, now)
    except Exception as exc:
        problems.append(("supabase:error", f"Supabase : contrôle impossible ({exc.__class__.__name__}: {exc})."))

    report = build_report(problems, notes, now)
    Path("health-report.md").write_text(report, encoding="utf-8")
    Path("health-signature.txt").write_text(
        " ".join(sorted(key for key, _ in problems)), encoding="utf-8",
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
