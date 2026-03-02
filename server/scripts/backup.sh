#!/bin/bash
# TotalReclaw Database Backup Script
# Usage: ./scripts/backup.sh [output_dir]
# Runs pg_dump inside the Docker container and saves a timestamped backup.
#
# Options:
#   output_dir    Directory to save backups (default: ./backups)
#
# Environment variables:
#   BACKUP_RETAIN  Number of backups to keep (default: 7)
#   CONTAINER_NAME Name of the Postgres container (default: totalreclaw-db)
#   POSTGRES_USER  Database user (default: totalreclaw)
#   POSTGRES_DB    Database name (default: totalreclaw)

set -euo pipefail

# Configuration
CONTAINER_NAME="${CONTAINER_NAME:-totalreclaw-db}"
POSTGRES_USER="${POSTGRES_USER:-totalreclaw}"
POSTGRES_DB="${POSTGRES_DB:-totalreclaw}"
BACKUP_RETAIN="${BACKUP_RETAIN:-7}"

# Resolve script directory so we can default output relative to server/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(dirname "$SCRIPT_DIR")"

# Output directory (argument or default)
OUTPUT_DIR="${1:-${SERVER_DIR}/backups}"

# Timestamp for filename
TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
BACKUP_FILE="totalreclaw_backup_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${OUTPUT_DIR}/${BACKUP_FILE}"

# ---------- Helpers ----------

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

# ---------- Pre-flight checks ----------

# Verify docker is available
command -v docker >/dev/null 2>&1 || die "docker is not installed or not in PATH"

# Verify the container is running
if ! docker inspect --format='{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q true; then
  die "Container '$CONTAINER_NAME' is not running. Start it with: docker-compose up -d"
fi

# Create output directory if needed
mkdir -p "$OUTPUT_DIR" || die "Cannot create output directory: $OUTPUT_DIR"

# ---------- Backup ----------

log "Starting backup of database '$POSTGRES_DB' from container '$CONTAINER_NAME'..."

# Run pg_dump inside the container and pipe through gzip on the host
if docker exec "$CONTAINER_NAME" \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --clean --if-exists \
  | gzip > "$BACKUP_PATH"; then

  # Verify the file was created and has content
  if [ ! -s "$BACKUP_PATH" ]; then
    rm -f "$BACKUP_PATH"
    die "Backup file is empty -- pg_dump may have failed silently"
  fi

  BACKUP_SIZE="$(du -h "$BACKUP_PATH" | cut -f1)"
  log "Backup complete: $BACKUP_PATH ($BACKUP_SIZE)"
else
  rm -f "$BACKUP_PATH"
  die "pg_dump failed"
fi

# ---------- Retention cleanup ----------

# Count existing backups (sorted oldest first)
BACKUP_COUNT=$(find "$OUTPUT_DIR" -maxdepth 1 -name 'totalreclaw_backup_*.sql.gz' -type f | wc -l | tr -d ' ')

if [ "$BACKUP_COUNT" -gt "$BACKUP_RETAIN" ]; then
  EXCESS=$((BACKUP_COUNT - BACKUP_RETAIN))
  log "Removing $EXCESS old backup(s) (retaining last $BACKUP_RETAIN)..."

  # Remove oldest backups beyond retention limit
  find "$OUTPUT_DIR" -maxdepth 1 -name 'totalreclaw_backup_*.sql.gz' -type f -print0 \
    | xargs -0 ls -1t \
    | tail -n "$EXCESS" \
    | while read -r old_backup; do
        log "  Removing: $(basename "$old_backup")"
        rm -f "$old_backup"
      done
fi

log "Done. $BACKUP_COUNT backup(s) in $OUTPUT_DIR (retention: $BACKUP_RETAIN)"
exit 0
