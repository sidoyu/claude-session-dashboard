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
#
# Optional:
#   SLACK_WEBHOOK_URL — if set, posts a one-line alert when the img/ folder
#                       exceeds 1 GiB (image attachments are kept outside the
#                       archive because they can be regenerated from the JSONL).
#   IMG_ALERT_BYTES   — override the 1 GiB threshold (default: 1073741824).

set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_NAME="$(basename "$SRC_DIR")"
BACKUP_DEST="${BACKUP_DEST:-$HOME/Backups/claude-dashboard}"
RETENTION="${RETENTION:-8}"
TIMESTAMP=$(date +%Y-%m-%d)

mkdir -p "$BACKUP_DEST"

OUT="$BACKUP_DEST/$SRC_NAME-$TIMESTAMP.tar.gz"

# img/ is derived from JSONL (regenerable via convert_session.py --force), so we
# keep it out of the archive to reduce backup size and write time.
tar czf "$OUT" -C "$(dirname "$SRC_DIR")" --exclude="$SRC_NAME/img" "$SRC_NAME"

# Keep only the N newest archives.
ls -t "$BACKUP_DEST"/"$SRC_NAME"-*.tar.gz 2>/dev/null \
  | tail -n +$((RETENTION + 1)) \
  | xargs -r rm -f

echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup OK: $OUT ($(du -h "$OUT" | cut -f1))"

# Monitor img/ size and alert if it grows beyond the threshold.
IMG_DIR="$SRC_DIR/img"
if [ -d "$IMG_DIR" ]; then
  IMG_BYTES=$(du -sk "$IMG_DIR" 2>/dev/null | awk '{print $1*1024}')
  IMG_HUMAN=$(du -sh "$IMG_DIR" 2>/dev/null | awk '{print $1}')
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $SRC_NAME/img size: $IMG_HUMAN"
  THRESHOLD="${IMG_ALERT_BYTES:-1073741824}"  # 1 GiB
  if [ "${IMG_BYTES:-0}" -gt "$THRESHOLD" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN $SRC_NAME/img exceeded threshold ($IMG_HUMAN > $THRESHOLD bytes)"
    if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
      TEXT=":warning: *$SRC_NAME/img exceeded threshold* — current size ${IMG_HUMAN}. Review cleanup policy ($IMG_DIR)."
      ESC=$(printf '%s' "$TEXT" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')
      curl -fsS -m 10 --retry 2 -X POST -H 'Content-Type: application/json' \
        --data "{\"text\":${ESC}}" "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
    fi
  fi
fi
