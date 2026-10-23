#!/usr/bin/env bash
# Rejoue la migration 20261023120000 sur un Postgres JETABLE avec des doublures minimales de Supabase.
# Ne touche aucune base réelle. Usage : PGHOST=... PGPORT=... PGUSER=postgres ./run.sh  (la base `sp_test` est recréée)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
mig="$here/../../migrations/20261023120000_story_projects.sql"
dropdb --if-exists sp_test && createdb sp_test
psql -q -d sp_test -v ON_ERROR_STOP=1 -f "$here/00_stub.sql"
psql -q -d sp_test -v ON_ERROR_STOP=1 -f "$mig"
psql -q -d sp_test -v ON_ERROR_STOP=1 -f "$mig"   # rejouable
psql -q -d sp_test -f "$here/01_seed.sql"
psql -q -d sp_test -f "$here/02_scenario.sql"
