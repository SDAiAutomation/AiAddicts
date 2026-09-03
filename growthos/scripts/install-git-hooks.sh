#!/usr/bin/env bash
# Point this repo's git hooks at growthos/scripts/githooks/.
# Repo-wide setting (git hooks are not per-subdirectory), but the pre-commit
# hook itself only inspects staged changes under growthos/.
set -e

root=$(git rev-parse --show-toplevel)
cd "$root"

existing=$(git config --local --get core.hooksPath || true)
if [ -n "$existing" ] && [ "$existing" != "growthos/scripts/githooks" ]; then
  echo "core.hooksPath deja defini sur '$existing' — non modifie."
  echo "Fusionne manuellement growthos/scripts/githooks/pre-commit si besoin."
  exit 1
fi

git config core.hooksPath growthos/scripts/githooks
chmod +x growthos/scripts/githooks/* 2>/dev/null || true

echo "core.hooksPath -> growthos/scripts/githooks"
echo "Garde-fou actif : blocage des cles service_role / ELEVENLABS_API_KEY dans tout commit touchant growthos/."
echo "Desactiver : git config --unset core.hooksPath"
