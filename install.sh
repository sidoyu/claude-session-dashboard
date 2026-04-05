#!/bin/bash
set -e

# ─── Claude Code Session Dashboard Installer ───
#
# 이 스크립트는 다음을 수행합니다:
# 1. 세션 JSONL → HTML 변환 (convert_session.py)
# 2. Claude Code Stop hook 등록 (세션 종료 시 자동 변환)
# 3. LaunchAgent 등록 (서버 자동 시작 + 재시작)
# 4. 서버 시작 및 브라우저 열기

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS_FILE="$HOME/.claude/settings.json"
PLIST_NAME="com.claude.session-dashboard"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PORT=18080

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Claude Code Session Dashboard — Installer   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─── 사전 확인 ───

# Python 3 확인
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3이 필요합니다. 설치 후 다시 실행해주세요."
    exit 1
fi

# Claude Code 세션 존재 확인
PROJECTS_BASE="$HOME/.claude/projects"
if [ ! -d "$PROJECTS_BASE" ]; then
    echo "❌ Claude Code 세션 디렉토리를 찾을 수 없습니다: $PROJECTS_BASE"
    echo "   Claude Code를 한 번 이상 사용한 후 다시 시도해주세요."
    exit 1
fi

SESSION_COUNT=$(find "$PROJECTS_BASE" -name "*.jsonl" -not -name "agent-*" 2>/dev/null | wc -l | tr -d ' ')
echo "✓ Python 3: $(python3 --version 2>&1)"
echo "✓ Claude Code 세션: ${SESSION_COUNT}개 발견"
echo "✓ 설치 경로: $SCRIPT_DIR"
echo ""

# ─── Step 1: 세션 변환 ───

echo "── Step 1/4: 세션을 HTML로 변환 중..."
python3 "$SCRIPT_DIR/convert_session.py" --force
echo ""

# ─── Step 2: Stop Hook 등록 ───

echo "── Step 2/4: Claude Code Stop hook 등록..."

HOOK_COMMAND="python3 ${SCRIPT_DIR}/convert_session.py"

# settings.json이 없으면 생성
if [ ! -f "$SETTINGS_FILE" ]; then
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    echo '{}' > "$SETTINGS_FILE"
fi

# Python으로 안전하게 JSON 병합
python3 << PYEOF
import json, sys, os

settings_path = "$SETTINGS_FILE"
hook_command = "$HOOK_COMMAND"

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

# hooks.Stop 배열 가져오기 (없으면 생성)
hooks = settings.setdefault('hooks', {})
stop_hooks = hooks.setdefault('Stop', [])

# 이미 등록되어 있는지 확인
already_exists = False
for entry in stop_hooks:
    # 이중 중첩 구조: { hooks: [{ command: ... }] }
    if isinstance(entry, dict) and 'hooks' in entry:
        for h in entry['hooks']:
            if h.get('command', '') == hook_command:
                already_exists = True
                break
    # 단일 구조: { command: ... }
    elif isinstance(entry, dict) and entry.get('command', '') == hook_command:
        already_exists = True
    if already_exists:
        break

if already_exists:
    print("  이미 등록되어 있습니다. 건너뜁니다.")
else:
    # 기존 hook 구조에 맞춰서 추가
    if stop_hooks and isinstance(stop_hooks[0], dict) and 'hooks' in stop_hooks[0]:
        # 이중 중첩 구조
        new_entry = {"hooks": [{"type": "command", "command": hook_command, "timeout": 30}]}
    else:
        # 단일 구조
        new_entry = {"type": "command", "command": hook_command, "timeout": 30}

    # 맨 앞에 추가 (세션 종료 시 가장 먼저 변환)
    stop_hooks.insert(0, new_entry)

    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print("  ✓ Stop hook 등록 완료")
PYEOF
echo ""

# ─── Step 3: LaunchAgent 등록 ───

echo "── Step 3/4: LaunchAgent 등록 (서버 자동 시작)..."

# 기존 것이 있으면 먼저 제거
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    sleep 1
fi

cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${SCRIPT_DIR}/active_server.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/server.log</string>
    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/server.log</string>
</dict>
</plist>
PLISTEOF

launchctl load "$PLIST_PATH"
sleep 2

# 서버 확인
if curl -s "http://localhost:${PORT}/whoami" >/dev/null 2>&1; then
    echo "  ✓ 서버 시작됨: http://localhost:${PORT}"
else
    echo "  ⚠ 서버가 아직 시작되지 않았을 수 있습니다. 잠시 후 확인해주세요."
fi
echo ""

# ─── Step 4: 완료 ───

echo "── Step 4/4: 브라우저 열기..."
open "http://localhost:${PORT}"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅ 설치 완료!                               ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  대시보드: http://localhost:${PORT}            ║"
echo "║                                              ║"
echo "║  서버는 로그인 시 자동으로 시작됩니다.         ║"
echo "║  세션 종료 시 HTML이 자동으로 갱신됩니다.      ║"
echo "║                                              ║"
echo "║  제거: ./uninstall.sh                        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 선택: API 키 안내
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "💡 팁: ANTHROPIC_API_KEY를 설정하면 세션 제목이 AI로 자동 요약됩니다."
    echo "   export ANTHROPIC_API_KEY=sk-ant-..."
    echo "   python3 ${SCRIPT_DIR}/convert_session.py --force"
    echo ""
fi
