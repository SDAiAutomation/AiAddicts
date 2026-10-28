#!/usr/bin/env python3
"""PreToolUse hook (Bash) for the GrowthOS engine.

Blocks commands that must stay a human decision: merging, pushing to the default branch or force-pushing,
direct calls to paid AI providers, enabling paid Story generation, printing the local .env (API keys),
remote database migrations. Exit code 2 blocks the call and shows the reason to Claude.
Standard library only. Fails open (exit 0) on unreadable input so it never blocks normal work by accident.
"""
import json
import re
import sys

RULES = [
    (r"\bgh\s+pr\s+merge\b", "Le merge d'une PR reste une décision humaine."),
    (r"\bgit\s+push\b[^\n;&|]*[\s:](master|main|growthos/mvp)(?=[\s;&|]|$)",
     "Pas de push direct sur la branche par défaut : passe par une branche et une PR."),
    (r"\bgit\s+push\b[^\n;&|]*(--force\b|\s-f\b)", "Pas de push forcé."),
    (r"api\.openai\.com|api\.elevenlabs\.io|api\.anthropic\.com|fal\.run|api\.replicate\.com|api\.lumalabs\.ai|ltx\.(io|video)|api\.klingai",
     "Appel direct à un fournisseur IA payant : interdit sans autorisation explicite."),
    (r"\bSTORY_(ANIMATION|GENERATION)_ENABLED\s*=\s*[\"']?1", "Activation d'une génération payante (drapeau Story) : décision humaine."),
    (r"\b(cat|less|more|head|tail|type|bat|strings|xxd)\b[^\n;&|]*(^|[\s/\\])\.env(?![.\w])",
     "Lecture du fichier .env (clés API) : interdit, les secrets ne doivent jamais apparaître dans la conversation."),
    (r"\bsupabase\s+(db\s+(push|reset)|migration\s+repair)\b", "Migration ou reset de la base distante : décision humaine."),
    (r"\b(sk|rk)_live_[A-Za-z0-9]", "Clé Stripe live détectée dans une commande."),
    # Note: rules are matched case-insensitively.
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = str((payload.get("tool_input") or {}).get("command") or "")
    except Exception:
        return 0
    for pattern, reason in RULES:
        if re.search(pattern, command, flags=re.IGNORECASE):
            sys.stderr.write(
                f"Bloqué par .claude/hooks/guard_bash.py — {reason}\n"
                "Arrête-toi ici, explique à l'utilisateur ce que tu voulais faire et laisse-le le faire "
                "lui-même ou l'autoriser explicitement.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
