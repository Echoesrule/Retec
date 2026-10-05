#!/usr/bin/env bash
#
# Restore the production database from a dump taken by tools/backup.sh.
#
#     bash tools/restore.sh backups/retec-20260930-120000.sql.gz
#     bash tools/restore.sh --dry-run backups/retec-....sql.gz   # stop before writing
#
# THIS IS DESTRUCTIVE. It runs a --clean dump, which drops and recreates
# every table. It is gated behind three things so it can never happen by
# accident, even if you have db_guard's opt-ins set:
#
#   1. RETEC_ALLOW_RESTORE=1
#   2. an interactive "type RESTORE" confirmation (skippable for automation
#      only with RETEC_CI=1, which also demands --yes)
#   3. the dump file must exist and pass a gzip integrity check first
#
# The app's own db_guard will additionally refuse if something in the stack
# tries drop_all() without its own confirming vars.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${RETEC_PROD_ENV:-$ROOT/.env.production}"
export PATH="${RETEC_PG_BIN:-$HOME/.local/pg}:$PATH"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; shift; fi
DUMP="${1:?usage: restore.sh [--dry-run] <dump.sql.gz>}"

bold "RETEC database restore"
echo

# ---- gate 1: explicit env var ----
if [[ "${RETEC_ALLOW_RESTORE:-}" != "1" ]]; then
  red "Refusing to restore: RETEC_ALLOW_RESTORE is not set to 1."
  echo
  echo "  This replaces ALL data in the production database."
  echo "  Read tools/restore.sh first, then re-run with:"
  echo
  echo "      RETEC_ALLOW_RESTORE=1 bash tools/restore.sh $DUMP"
  echo
  exit 1
fi

# ---- gate 2: the dump must exist and be intact ----
if [[ ! -f "$DUMP" ]]; then
  red "No such dump: $DUMP"
  echo "  List what you have with:  bash tools/backup.sh --list"
  exit 1
fi
if ! gzip -t "$DUMP" 2>/dev/null; then
  red "Dump failed gzip integrity check -- it is corrupt, refusing to use it."
  exit 1
fi

TABLES=$(gzip -dc "$DUMP" | grep -c '^CREATE TABLE' || true)
ROWS=$(gzip -dc "$DUMP" | grep -c '^COPY ' || true)
bold "About to restore:"
echo "  dump    : $DUMP"
echo "  tables  : $TABLES"
echo "  with data: $ROWS"
if [[ "$TABLES" -eq 0 ]]; then
  red "Dump contains no tables. Refusing."
  exit 1
fi
echo

# ---- gate 3: human confirmation ----
if [[ "${RETEC_CI:-}" != "1" || "${ASSUME_YES:-0}" != "1" ]]; then
  printf '  Type RESTORE to proceed (anything else aborts): '
  read -r answer
  if [[ "$answer" != "RESTORE" ]]; then
    red "Aborted. Nothing was changed."
    exit 1
  fi
fi

# ---- resolve connection (session pooler, not transaction pooler) ----
# Parsing lives in tools/_dburl.py (urllib-based, unit tested) rather than in
# shell string surgery; see tools/test_dburl.py.
url_field() {
  "${RETEC_PYTHON:-python3}" "$ROOT/tools/_dburl.py" "$1" "$2"
}
url_pass() {
  "${RETEC_PYTHON:-python3}" -c \
    'import sys; sys.path.insert(0, sys.argv[1]); import _dburl; print(_dburl.parse(sys.argv[2])["pass"])' \
    "$ROOT/tools" "$1"
}
prod_url() {
  grep -E '^[[:space:]]*DATABASE_URL=' "$ENV_FILE" \
    | head -1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

[[ -f "$ENV_FILE" ]] || { red "No $ENV_FILE"; exit 1; }
url="$(prod_url)"
[[ -n "$url" ]] || { red "DATABASE_URL missing in $ENV_FILE"; exit 1; }

user="$(url_field "$url" user)"; pass="$(url_pass "$url")"
host="$(url_field "$url" host)"; port="$(url_field "$url" session_port)"
dbname="$(url_field "$url" dbname)"

echo
echo "  target  : $host:$port/$dbname"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  green "DRY RUN -- would restore $TABLES tables / $ROWS populated tables into $dbname."
  echo "  Connection is not attempted. Remove --dry-run to actually do it."
  exit 0
fi

# Take a safety copy of the CURRENT state first, so a bad restore is itself
# recoverable. This is the step that was missing on 2026-09-30.
echo
echo "  Safety backup of current state first..."
if bash "$ROOT/tools/backup.sh" >/tmp/.retec_pre_restore 2>&1; then
  green "  pre-restore backup saved (see --list)"
else
  red "  pre-restore backup FAILED. Refusing to restore."
  cat /tmp/.retec_pre_restore
  exit 1
fi
rm -f /tmp/.retec_pre_restore

export PGPASSWORD="$pass"
export PGSSLMODE="${PGSSLMODE:-require}"

echo
echo "  Restoring (this drops and recreates every table)..."
if ! psql --host="$host" --port="$port" --username="$user" --dbname="$dbname" \
      --quiet --set ON_ERROR_STOP=1 --file <(gzip -dc "$DUMP"); then
  unset PGPASSWORD
  red
  red "RESTORE FAILED partway. The database may be in a partial state."
  echo "  Your pre-restore backup is intact -- re-run this script pointing at it:"
  bash "$ROOT/tools/backup.sh" --list
  exit 1
fi
unset PGPASSWORD

echo
green "Restore complete: $TABLES tables, $ROWS populated."
echo "  Verify the site loads, then consider re-running a backup."
