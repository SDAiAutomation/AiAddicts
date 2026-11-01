"""Pré-vérification du pilote payant Story Visual : HORS LIGNE, lecture seule.

N'appelle AUCUN fournisseur, n'ouvre AUCUNE connexion réseau, n'écrit rien, ne lit AUCUN fichier d'environnement (uniquement les variables du
processus) et n'affiche JAMAIS la valeur d'un secret (« présente » / « absente »). Il dit si la configuration du worker de TEST est prête
pour un épisode pilote, ou ce qui manque. Il ne lance rien : lancer l'épisode demande l'autorisation explicite du propriétaire.

    python scripts/story_visual_pilot_preflight.py [--max-usd 1.0] [--plan plan.json]

Code de sortie : 0 = aucun point bloquant ; 1 = au moins un point bloquant (FAIL).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from growthos.engine import image_model_router  # noqa: E402
from growthos.engine.story_visual import cost, ledger, sample, schema  # noqa: E402

SECRETS = ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "SUPABASE_SERVICE_ROLE_KEY")
MEASURED_MODEL, MEASURED_QUALITY, MEASURED_IMAGE_USD = "gpt-image-2.5-flare", "low", 0.0092  # pilote artistique : 7 images = 0,0643 $
DEFAULT_PILOT_CAP = 1.00

SQL_CHECKS = (
    "-- à exécuter par un humain sur la base de TEST (lecture seule) :",
    "select conname, pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.content_assets'::regclass;  -- unique (content_item_id, kind, input_hash) ET check kind in (voice, voice_words, image)",
    "select count(*) from public.content_assets where input_hash like 'story-visual-ledger-%';  -- registre de dépense : 0 avant le pilote",
    "select count(*) from public.product_events where event = 'generation_started' and props->>'renderer' = 'story_visual';  -- requête du quota partagé : doit s'exécuter sans erreur",
)


def _num(env: dict, name: str):
    raw = (env.get(name) or "").strip()
    try:
        value = float(raw) if raw else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) and value >= 0 else None


def run_checks(env: dict, plan: dict, max_usd: float) -> list[tuple[str, str, str]]:
    """[(statut, point, détail)] ; statut ∈ OK | FAIL | WARN | INFO. Aucune valeur de secret n'est jamais renvoyée."""
    out: list[tuple[str, str, str]] = []
    add = lambda status, point, detail: out.append((status, point, detail))  # noqa: E731

    enabled = env.get("STORY_VISUAL_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
    add("WARN" if enabled else "INFO", "drapeau moteur STORY_VISUAL_ENABLED",
        "ACTIVÉ sur ce processus : à ne faire que sur l'environnement de test, pendant le pilote" if enabled else "éteint (normal avant le pilote)")
    add("OK" if (env.get("ADMIN_USER_IDS") or "").strip() else "FAIL", "ADMIN_USER_IDS", "présente" if (env.get("ADMIN_USER_IDS") or "").strip() else "absente : le moteur refuse tout appelant")
    for name in SECRETS:
        present = bool((env.get(name) or "").strip())
        add("OK" if present else "FAIL", name, "présente" if present else "absente")
    add("OK" if (env.get("SUPABASE_URL") or "").strip() else "FAIL", "SUPABASE_URL", "présente" if (env.get("SUPABASE_URL") or "").strip() else "absente")

    selection = image_model_router.select_model("final")
    exact = (selection.model, selection.quality) == (MEASURED_MODEL, MEASURED_QUALITY)
    add("OK" if exact else "WARN", "modèle d'image (final)", f"{selection.model} / {selection.quality}" + ("" if exact else f" : le coût n'a été mesuré que pour {MEASURED_MODEL} / {MEASURED_QUALITY} (IMAGE_MODEL_PREMIUM, IMAGE_FINAL_QUALITY)"))

    unit, source = cost.image_unit_cost(env)
    if unit is None:
        add("FAIL", "tarif d'une image", "non configuré (STORY_IMAGE_USD_EACH) : le moteur refuse un coût inconnu")
    else:
        add("OK" if unit >= MEASURED_IMAGE_USD else "WARN", "tarif d'une image", f"{unit} $ ({source})" + ("" if unit >= MEASURED_IMAGE_USD else f" : inférieur au coût mesuré ({MEASURED_IMAGE_USD} $)"))
    for name, label in (("ELEVENLABS_USD_PER_1K_CHARS", "tarif de la voix ($ / 1 000 caractères)"), ("STORY_RENDER_USD", "coût de rendu"), ("STORY_STORAGE_USD", "coût de stockage")):
        value = _num(env, name)
        add("OK" if value is not None else "FAIL", label, f"{value} $ ({name})" if value is not None else f"non configuré ({name}) ; 0 est une valeur valide si l'exécuteur est déjà payé")
    script_ok = all(_num(env, n) is not None for n in ("SCRIPT_PRICE_IN_PER_M", "SCRIPT_PRICE_OUT_PER_M", "STORY_PLAN_TOKENS_IN", "STORY_PLAN_TOKENS_OUT"))
    add("OK" if script_ok else "FAIL", "coût du planificateur", "configuré" if script_ok else "non configuré : le pilote fournit le plan (aucun appel au planificateur), déclarer 0 explicitement (SCRIPT_PRICE_*, STORY_PLAN_TOKENS_*)")

    cap, target = _num(env, "STORY_BUDGET_USD"), _num(env, "STORY_BUDGET_PREFERRED_USD")
    if cap is None:
        add("FAIL", "plafond STORY_BUDGET_USD", f"non défini (la valeur par défaut serait {cost.DEFAULT_BUDGET_USD} $) : le fixer explicitement, au plus {max_usd} $ pour le pilote")
    else:
        add("OK" if cap <= max_usd else "FAIL", "plafond STORY_BUDGET_USD", f"{cap} $" + ("" if cap <= max_usd else f" : supérieur au plafond de pilote ({max_usd} $)"))
    if target is not None and cap is not None and target > cap:
        add("WARN", "cible STORY_BUDGET_PREFERRED_USD", "supérieure au plafond (sera ramenée au plafond)")

    errors = schema.validate_story_plan(plan)
    add("OK" if not errors else "FAIL", "plan de l'épisode", f"{len(plan.get('scenes', []))} scènes, valide" if not errors else "invalide : " + "; ".join(errors[:3]))
    has_voice = bool(plan.get("voice_id")) or bool((env.get("STORY_DEFAULT_VOICE_ID") or "").strip())
    add("OK" if has_voice else "FAIL", "voix", "configurée (plan.voice_id ou STORY_DEFAULT_VOICE_ID)" if has_voice else "aucune voix : plan.voice_id ou STORY_DEFAULT_VOICE_ID")

    per_story = int(_num(env, "STORY_MAX_STORY_REGENERATIONS") if _num(env, "STORY_MAX_STORY_REGENERATIONS") is not None else 6)
    if not errors:
        base = cost.estimate_episode(plan, env)
        worst = cost.estimate_episode(plan, env, regenerations=per_story)
        budget = cost.Budget(cap if cap is not None else cost.DEFAULT_BUDGET_USD, target if target is not None else cost.PREFERRED_BUDGET_USD)
        decision = cost.check_budget(worst, budget)
        if base["unpriced"]:
            add("FAIL", "estimation de l'épisode", "non chiffrée : " + ", ".join(base["unpriced"]))
        else:
            add("OK" if decision["allowed"] else "FAIL", "estimation de l'épisode",
                f"{base['total_usd']} $ nominal ; {worst['total_usd']} $ au pire ({per_story} régénérations) ; {decision['message']}")
    jobs = _num(env, "STORY_VISUAL_MAX_JOBS_PER_DAY")
    add("OK" if jobs is not None and jobs <= 1 else "WARN", "quota STORY_VISUAL_MAX_JOBS_PER_DAY",
        f"{int(jobs)}" if jobs is not None else "non défini (défaut 3) : le fixer à 1 pour le pilote")

    add("OK" if ledger.KIND in ("voice", "voice_words", "image") and 16 <= len(ledger.LEDGER_PREFIX) + 6 <= 64 else "FAIL", "registre de dépense (invariants statiques)", f"kind={ledger.KIND}, clé de {len(ledger.LEDGER_PREFIX) + 6} caractères")
    for line in SQL_CHECKS:
        add("INFO", "base de test", line)
    return out


def main(argv: list[str] | None = None, env: dict | None = None, out=print) -> int:
    parser = argparse.ArgumentParser(description="Pré-vérification hors ligne du pilote payant Story Visual (ne lance rien).")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_PILOT_CAP, help="plafond de dépense du pilote (défaut 1,00 $)")
    parser.add_argument("--plan", help="plan JSON à vérifier (défaut : la fable d'exemple du moteur)")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if args.plan else sample.moral_plan()
    out("Pré-vérification Story Visual — hors ligne : aucun appel réseau, aucun fournisseur, aucune écriture, aucun secret affiché.")
    checks = run_checks(env, plan, args.max_usd)
    for status, point, detail in checks:
        out(f"[{status:<4}] {point} : {detail}")
    failures = [p for s, p, _ in checks if s == "FAIL"]
    out("VERDICT : " + ("PRÊT (aucun point bloquant) — le lancement reste soumis à l'autorisation explicite du propriétaire." if not failures else f"NON PRÊT — {len(failures)} point(s) bloquant(s) : " + "; ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
