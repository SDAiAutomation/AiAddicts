#!/usr/bin/env bash
# Rejoue toutes les migrations puis le scenario Instagram sur un Postgres JETABLE (doublures Supabase).
# Ne touche aucune base reelle. Usage : PGHOST=127.0.0.1 PGUSER=postgres ./run.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
migrations="$here/../../migrations"
db=meta_instagram_test
dropdb --if-exists "$db" && createdb "$db"
psql -q -d "$db" -v ON_ERROR_STOP=1 -c 'create extension if not exists pgcrypto' -f "$here/00_stub.sql"
apply() { sed -E '/create extension if not exists (pg_cron|pg_net)/Id' "$1" | psql -q -d "$db" -v ON_ERROR_STOP=1 -f - ; }
for file in "$migrations"/*.sql; do apply "$file"; done
new="$migrations/20261108120000_meta_instagram_social_publications.sql"
apply "$new" # rejouable
psql -q -d "$db" -v ON_ERROR_STOP=1 -f "$here/02_scenario.sql"
echo "META_INSTAGRAM_SQL_OK"
