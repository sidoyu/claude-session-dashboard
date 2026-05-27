#!/bin/bash
# Claude Code Session Dashboard — cron sweep
#
# 1분마다 실행되어 변경된 JSONL만 HTML로 변환한다.
# Stop hook race condition (JSONL 마지막 라인 flush 전 hook 발화)을 회피하기 위한 단일 메커니즘.
#
# 환경변수 (옵션):
#   HEALTHCHECKS_URL   — 설정 시 healthchecks.io 등 외부 모니터링에 ping 송신
#   PYTHON_BIN         — python 경로 (기본: python3)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/cron.log"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT="${SCRIPT_DIR}/convert_session.py"

ping_hc() {
  [ -n "${HEALTHCHECKS_URL:-}" ] || return 0
  curl -fsS -m 10 --retry 3 "${HEALTHCHECKS_URL}${1:-}" >/dev/null 2>&1 || true
}

on_exit() {
  local code=$?
  if [ $code -ne 0 ]; then
    ping_hc "/fail"
  fi
}
trap 'on_exit' EXIT

# 로그 로테이션: 10MB 초과 시 마지막 5MB만 보존
if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt 10485760 ]; then
  tail -c 5242880 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

ping_hc "/start"
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') cron-sweep start ==="
  "$PYTHON_BIN" "$SCRIPT"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') cron-sweep end ==="
} >> "$LOG_FILE" 2>&1

ping_hc ""
