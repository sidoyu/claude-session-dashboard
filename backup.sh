#!/bin/bash
# Weekly backup of the dashboard directory to a configurable destination.
# Designed to be run from cron, e.g.:
#   0 3 * * 0  /path/to/dashboard/backup.sh   # every Sunday at 03:00
#
# Defaults:
#   - Source:      directory containing this script
#   - Destination: ~/Backups/claude-dashboard
#   - Retention:   8 most recent archives
#
# Override via environment variables:
#   BACKUP_DEST=/path/to/dest  RETENTION=12  ./backup.sh

set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_NAME="$(basename "$SRC_DIR")"
BACKUP_DEST="${BACKUP_DEST:-$HOME/Backups/claude-dashboard}"
RETENTION="${RETENTION:-8}"
TIMESTAMP=$(date +%Y-%m-%d)

mkdir -p "$BACKUP_DEST"

OUT="$BACKUP_DEST/$SRC_NAME-$TIMESTAMP.tar.gz"

tar czf "$OUT" -C "$(dirname "$SRC_DIR")" "$SRC_NAME"

# Keep only the N newest archives.
ls -t "$BACKUP_DEST"/"$SRC_NAME"-*.tar.gz 2>/dev/null \
  | tail -n +$((RETENTION + 1)) \
  | xargs -r rm -f

echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup OK: $OUT ($(du -h "$OUT" | cut -f1))"
