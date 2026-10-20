#!/usr/bin/env bash
# Rejoue la migration 20261020180000 sur un Postgres JETABLE avec des doublures minimales de Supabase
# (auth.uid/role, schéma internal, tables de base). Ne touche aucune base réelle.
# Usage : PGHOST=127.0.0.1 PGPORT=5544 PGUSER=postgres ./run.sh   (la base `qce_test` est recréée)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
mig="$here/../../migrations/20261020180000_quiz_chapter_exports.sql"
dropdb --if-exists qce_test && createdb qce_test
psql -q -d qce_test -v ON_ERROR_STOP=1 -f "$here/00_stub.sql"
psql -q -d qce_test -v ON_ERROR_STOP=1 -f "$mig"
psql -q -d qce_test -v ON_ERROR_STOP=1 -f "$mig"   # rejouable
psql -q -d qce_test -f "$here/01_seed.sql"
psql -q -d qce_test -f "$here/02_scenario.sql"
echo "Relire la sortie : chaque section annonce le nombre de lignes/erreurs attendu."
