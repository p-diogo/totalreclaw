#!/bin/bash
# OpenMemory Database Restore Script
# Usage: ./scripts/restore.sh <backup_file> [--force]
# WARNING: This will DROP and recreate the database!
#
# Arguments:
#   backup_file   Path to a .sql or .sql.gz backup file
#   --force       Skip confirmation prompt
#
# Environment variables:
#   CONTAINER_NAME Name of the Postgres container (default: openmemory-db)
#   POSTGRES_USER  Database user (default: openmemory)
#   POSTGRES_DB    Database name (default: openmemory)

set -euo pipefail

# Configuration
CONTAINER_NAME="${CONTAINER_NAME:-openmemory-db}"
POSTGRES_USER="${POSTGRES_USER:-openmemory}"
POSTGRES_DB="${POSTGRES_DB:-openmemory}"

FORCE=false

# ---------- Helpers ----------

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

usage() {
  echo "Usage: $0 <backup_file> [--force]"
  echo ""
  echo "Arguments:"
  echo "  backup_file   Path to a .sql or .sql.gz backup file"
  echo "  --force       Skip confirmation prompt"
  echo ""
  echo "WARNING: This will DROP and recreate the '$POSTGRES_DB' database!"
  exit 1
}

# ---------- Argument parsing ----------

BACKUP_FILE=""

for arg in "$@"; do
  case "$arg" in
    --force)
      FORCE=true
      ;;
    -h|--help)
      usage
      ;;
    *)
      if [ -z "$BACKUP_FILE" ]; then
        BACKUP_FILE="$arg"
      else
        die "Unexpected argument: $arg"
      fi
      ;;
  esac
done

if [ -z "$BACKUP_FILE" ]; then
  usage
fi

# ---------- Pre-flight checks ----------

# Verify docker is available
command -v docker >/dev/null 2>&1 || die "docker is not installed or not in PATH"

# Verify the container is running
if ! docker inspect --format='{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q true; then
  die "Container '$CONTAINER_NAME' is not running. Start it with: docker-compose up -d"
fi

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
  die "Backup file not found: $BACKUP_FILE"
fi

# Determine if file is gzipped
IS_GZIPPED=false
case "$BACKUP_FILE" in
  *.sql.gz)
    IS_GZIPPED=true
    ;;
  *.sql)
    IS_GZIPPED=false
    ;;
  *)
    die "Unsupported file format. Expected .sql or .sql.gz"
    ;;
esac

BACKUP_SIZE="$(du -h "$BACKUP_FILE" | cut -f1)"
log "Backup file: $BACKUP_FILE ($BACKUP_SIZE)"

# ---------- Confirmation ----------

if [ "$FORCE" != true ]; then
  echo ""
  echo "============================================================"
  echo "  WARNING: This will DESTROY all data in '$POSTGRES_DB'"
  echo "  and restore from: $(basename "$BACKUP_FILE")"
  echo "============================================================"
  echo ""
  read -r -p "Are you sure you want to proceed? [y/N] " response
  case "$response" in
    [yY][eE][sS]|[yY])
      log "Proceeding with restore..."
      ;;
    *)
      log "Restore cancelled."
      exit 0
      ;;
  esac
fi

# ---------- Drop and recreate database ----------

log "Terminating active connections to '$POSTGRES_DB'..."
docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();" \
  >/dev/null 2>&1 || true

log "Dropping database '$POSTGRES_DB'..."
docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -c \
  "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";" \
  || die "Failed to drop database"

log "Creating database '$POSTGRES_DB'..."
docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -c \
  "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";" \
  || die "Failed to create database"

# ---------- Restore ----------

log "Restoring from backup..."

if [ "$IS_GZIPPED" = true ]; then
  # Decompress and pipe into psql inside the container
  if gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER_NAME" \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --single-transaction -q 2>&1; then
    log "Restore completed successfully."
  else
    die "Restore failed. The database may be in an inconsistent state."
  fi
else
  # Pipe uncompressed SQL into psql inside the container
  if docker exec -i "$CONTAINER_NAME" \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" --single-transaction -q < "$BACKUP_FILE" 2>&1; then
    log "Restore completed successfully."
  else
    die "Restore failed. The database may be in an inconsistent state."
  fi
fi

# ---------- Verify ----------

log "Verifying restore..."
TABLE_COUNT=$(docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
  | tr -d ' ')

if [ "$TABLE_COUNT" -gt 0 ]; then
  log "Verification passed: $TABLE_COUNT table(s) found in '$POSTGRES_DB'"

  # Print table summary
  docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
     FROM pg_tables
     WHERE schemaname = 'public'
     ORDER BY tablename;"
else
  log "WARNING: No tables found after restore. The backup may have been empty."
fi

log "Done."
exit 0
