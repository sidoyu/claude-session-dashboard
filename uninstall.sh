#!/bin/bash
set -e

# ─── Claude Code Session Dashboard Uninstaller ───

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS_FILE="$HOME/.claude/settings.json"
PLIST_NAME="com.claude.session-dashboard"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo ""
echo "Claude Code Session Dashboard — 제거"
echo ""

# ─── 1. LaunchAgent 제거 ───

if [ -f "$PLIST_PATH" ]; then
    echo "  LaunchAgent 제거 중..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "  ✓ LaunchAgent 제거됨"
else
    echo "  LaunchAgent 없음 (건너뜀)"
fi

# ─── 2. Stop Hook 제거 ───

if [ -f "$SETTINGS_FILE" ]; then
    echo "  Stop hook 제거 중..."
    HOOK_COMMAND="python3 ${SCRIPT_DIR}/convert_session.py"

    python3 << PYEOF
import json

settings_path = "$SETTINGS_FILE"
hook_command = "$HOOK_COMMAND"

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

stop_hooks = settings.get('hooks', {}).get('Stop', [])
original_count = len(stop_hooks)

# 해당 hook 제거
new_hooks = []
for entry in stop_hooks:
    if isinstance(entry, dict) and 'hooks' in entry:
        filtered = [h for h in entry['hooks'] if h.get('command', '') != hook_command]
        if filtered:
            entry['hooks'] = filtered
            new_hooks.append(entry)
    elif isinstance(entry, dict) and entry.get('command', '') == hook_command:
        continue
    else:
        new_hooks.append(entry)

if len(new_hooks) != original_count:
    settings['hooks']['Stop'] = new_hooks
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print("  ✓ Stop hook 제거됨")
else:
    print("  Stop hook 없음 (건너뜀)")
PYEOF
else
    echo "  settings.json 없음 (건너뜀)"
fi

# ─── 3. 생성된 파일 정리 ───

echo "  생성된 HTML 파일 정리 중..."
rm -f "$SCRIPT_DIR"/*.html
rm -f "$SCRIPT_DIR"/summaries.json
rm -f "$SCRIPT_DIR"/hidden_sessions.json
rm -f "$SCRIPT_DIR"/search_index.json
rm -f "$SCRIPT_DIR"/server.log
rm -f "$SCRIPT_DIR"/config.json
echo "  ✓ 생성 파일 정리됨"

echo ""
echo "✅ 제거 완료. 이 디렉토리(${SCRIPT_DIR})는 수동으로 삭제하세요:"
echo "   rm -rf ${SCRIPT_DIR}"
echo ""
