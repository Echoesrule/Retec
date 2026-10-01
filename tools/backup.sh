#!/usr/bin/env bash
#
# Back up the production database to a timestamped, gzipped SQL dump.
#
#     bash tools/backup.sh              # dump production
#     bash tools/backup.sh --list       # show existing backups + their contents
#     bash tools/backup.sh --verify F   # sanity-check one dump
#
# READ-ONLY. This never writes to the database, so it does not require the
# db_guard opt-in flags. It does require .env.production to exist.
#
# ---- why this is its own script and not "just use the Supabase dashboard" ----
# The free Supabase plan has no point-in-time recovery, which is how the
# 2026-09-30 data loss became permanent. Backups have to live outside
# Supabase, on a schedule, or they are not backups.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP_DIR="${RETEC_BACKUP_DIR:-$ROOT/backups}"
KEEP="${RETEC_BACKUP_KEEP:-30}"
ENV_FILE="${RETEC_PROD_ENV:-$ROOT/.env.production}"

# pg_dump/psql are not packaged with Ubuntu's default install, so they were
# extracted to ~/.local/pg. Override RETEC_PG_BIN if you later install them
# system-wide.
export PATH="${RETEC_PG_BIN:-$HOME/.local/pg}:$PATH"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

# --------------------------------------------------------------------------
# Read DATABASE_URL out of the production env file without sourcing it.
# Sourcing is avoided because .env.production is a key=value file that may
# contain characters bash would interpret.
# --------------------------------------------------------------------------
prod_url() {
  grep -E '^[[:space:]]*DATABASE_URL=' "$ENV_FILE" \
    | head -1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# URL parsing lives in tools/_dburl.py (urllib-based, unit tested) because
# getting host/port/dbname wrong by shell-string-surgery means dumping the
# wrong database. See tools/test_dburl.py.
url_field() {  # url_field <url> <user|host|port|dbname|session_port>
  "${RETEC_PYTHON:-python3}" "$ROOT/tools/_dburl.py" "$1" "$2"
}

url_pass() {  # not exposed via the CLI: the CLI refuses to print passwords
  "${RETEC_PYTHON:-python3}" -c \
    'import sys; sys.path.insert(0, sys.argv[1]); import _dburl; print(_dburl.parse(sys.argv[2])["pass"])' \
    "$ROOT/tools" "$1"
}

require_tools() {
  command -v pg_dump >/dev/null 2>&1 || {
    red "pg_dump not found. Set RETEC_PG_BIN to the directory containing it."; exit 1; }
  command -v gzip    >/dev/null 2>&1 || { red "gzip not found."; exit 1; }
  "${RETEC_PYTHON:-python3}" -c 'import sys; sys.exit(0)' || {
    red "python3 not found; needed to parse the database URL."; exit 1; }
}

show_dumps() {
  bold "Backups in $BACKUP_DIR:"
  if ! compgen -G "$BACKUP_DIR/*.sql.gz" >/dev/null; then
    echo "  (none yet)"
    return
  fi
  for f in $(ls -1t "$BACKUP_DIR"/*.sql.gz); do
    local size rows
    size=$(du -h "$f" | cut -f1)
    # Count COPY data lines as a cheap "does this have data?" signal.
    rows=$(gzip -dc "$f" 2>/dev/null | grep -c '^COPY ' || true)
    printf '  %-52s %6s  %s tables with data\n' "$(basename "$f")" "$size" "$rows"
  done
}

verify_dump() {
  local f="${1:?usage: backup.sh --verify <file.sql.gz>}"
  [[ -f "$f" ]] || { red "no such file: $f"; exit 1; }
  bold "Verifying $f"
  gzip -t "$f"                 || { red "gzip integrity check FAILED"; exit 1; }
  green "  gzip integrity      ok"
  gzip -dc "$f" | grep -q 'CREATE TABLE' || { red "no CREATE TABLE found"; exit 1; }
  green "  contains schema     ok"
  local tables rows
  tables=$(gzip -dc "$f" | grep -c '^CREATE TABLE' || true)
  rows=$(gzip -dc "$f" | grep -c '^COPY ' || true)
  green "  $tables tables, $rows with data"
  [[ "$rows" -gt 0 ]] || { red "  WARNING: dump has schema but zero rows"; }
}

do_backup() {
  require_tools

  if [[ ! -f "$ENV_FILE" ]]; then
    red "No $ENV_FILE -- cannot find production credentials."
    echo "  Expected a file with DATABASE_URL=<full postgres url>."
    exit 1
  fi

  local url; url="$(prod_url)"
  [[ -n "$url" ]] || { red "DATABASE_URL missing or empty in $ENV_FILE"; exit 1; }

  local user pass host port dbname real_port
  user="$(url_field "$url" user)"
  pass="$(url_pass  "$url")"
  host="$(url_field "$url" host)"
  port="$(url_field "$url" port)"
  dbname="$(url_field "$url" dbname)"
  real_port="$(url_field "$url" session_port)"

  mkdir -p "$BACKUP_DIR"
  local stamp out
  stamp="$(date +%Y%m%d-%H%M%S)"
  out="$BACKUP_DIR/retec-$stamp.sql.gz"

  bold "RETEC database backup"
  echo "  host     : $host:$real_port   (was :$port in .env.production)"
  if [[ "$port" != "$real_port" ]]; then
    echo "             ^ rewritten 6543 -> 5432; pg_dump cannot use the transaction pooler"
  fi
  echo "  database : $dbname"
  echo "  output   : $out"
  echo "  keep     : last $KEEP dumps"
  echo

  # PGPASSWORD keeps the secret out of the process list (ps) and out of shell
  # history, which a URL on the command line would not.
  export PGPASSWORD="$pass"
  # Supabase's pooler terminates TLS; prefer it even if the URL omitted sslmode.
  export PGSSLMODE="${PGSSLMODE:-require}"

  # --clean --if-exists keeps restores idempotent.
  # No --no-owner/--no-acl: we want the dump to be restorable by the same
  # role that took it, and Supabase does not grant CREATEROLE.
  if ! pg_dump \
        --host="$host" --port="$real_port" --username="$user" --dbname="$dbname" \
        --clean --if-exists --no-owner --no-privileges \
        --format=plain --compress=0 \
        2>/tmp/.retec_pgdump_err | gzip -9 > "$out"; then
    red "pg_dump FAILED:"
    cat /tmp/.retec_pgdump_err >&2
    rm -f "$out"
    exit 1
  fi
  unset PGPASSWORD

  if [[ -s /tmp/.retec_pgdump_err ]]; then
    yellow_warn="$(cat /tmp/.retec_pgdump_err)"
    red "pg_dump wrote warnings:"
    echo "$yellow_warn"
  fi
  rm -f /tmp/.retec_pgdump_err

  # ---- never keep a backup we have not verified ----
  gzip -t "$out" || { red "gzip integrity check failed, discarding"; rm -f "$out"; exit 1; }
  local tables rows
  tables=$(gzip -dc "$out" | grep -c '^CREATE TABLE' || true)
  rows=$(gzip -dc "$out" | grep -c '^COPY ' || true)
  if [[ "$tables" -eq 0 ]]; then
    red "Dump has no tables -- treating as failure and discarding."
    rm -f "$out"
    exit 1
  fi

  echo
  green "Backup OK: $(du -h "$out" | cut -f1), $tables tables, $rows with data"

  if [[ "$rows" -eq 0 ]]; then
    red "WARNING: zero rows in the dump. If you have content, something is wrong."
  fi

  # ---- rotation ----
  local old
  old=$(ls -1t "$BACKUP_DIR"/retec-*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" || true)
  if [[ -n "$old" ]]; then
    echo "$old" | while read -r f; do
      echo "  pruning $(basename "$f")"
      rm -f "$f"
    done
  fi

  echo
  bold "Recent backups:"
  show_dumps
  echo
  echo "  Restore with:  bash tools/restore.sh $out"
}

case "${1:-}" in
  --list)   require_tools; show_dumps ;;
  --verify) require_tools; shift; verify_dump "${1:?usage: backup.sh --verify <file>}" ;;
  -h|--help|help)
    sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  "")       do_backup ;;
  *)        red "unknown option: $1"; sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
