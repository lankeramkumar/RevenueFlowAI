#!/usr/bin/env bash
# Backup and restore drill for the Compose Postgres. Dumps the live database,
# restores the dump into a scratch database, compares row counts for every
# table, and drops the scratch database. Never touches the live database.
set -euo pipefail

DB_SERVICE=${DB_SERVICE:-db}
SRC_DB=${SRC_DB:-revenueflow}
SCRATCH_DB=${SCRATCH_DB:-revenueflow_restore_drill}
DUMP=${DUMP:-/tmp/revenueflow.dump}
COMPOSE="docker compose"

psql_in() { $COMPOSE exec -T "$DB_SERVICE" psql -U revenueflow -d "$1" -v ON_ERROR_STOP=1 -At -c "$2"; }

echo "1. Dump $SRC_DB (custom format)"
$COMPOSE exec -T "$DB_SERVICE" pg_dump -U revenueflow -Fc "$SRC_DB" > "$DUMP"
echo "   dump bytes: $(wc -c < "$DUMP")"

echo "2. Create scratch database $SCRATCH_DB"
psql_in postgres "DROP DATABASE IF EXISTS $SCRATCH_DB;"
psql_in postgres "CREATE DATABASE $SCRATCH_DB;"

echo "3. Restore into $SCRATCH_DB"
$COMPOSE exec -T "$DB_SERVICE" pg_restore -U revenueflow -d "$SCRATCH_DB" --no-owner < "$DUMP"

echo "4. Compare row counts"
TABLES=$(psql_in "$SRC_DB" "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;")
FAIL=0
for t in $TABLES; do
  src=$(psql_in "$SRC_DB" "SELECT count(*) FROM \"$t\";")
  dst=$(psql_in "$SCRATCH_DB" "SELECT count(*) FROM \"$t\";")
  if [ "$src" != "$dst" ]; then echo "   MISMATCH $t: source=$src restored=$dst"; FAIL=1; fi
done
echo "   tables compared: $(echo "$TABLES" | wc -w)"

echo "5. Drop scratch database"
psql_in postgres "DROP DATABASE $SCRATCH_DB;"
rm -f "$DUMP"

if [ "$FAIL" -ne 0 ]; then echo "RESTORE DRILL FAILED"; exit 1; fi
echo "RESTORE DRILL PASSED"
