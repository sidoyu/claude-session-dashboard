#!/bin/bash
set -euo pipefail

# ─── Claude Code Session Dashboard Installer ───
#
# Usage:
#   ./install.sh          # 인터랙티브 모드 (사람이 직접 실행)
#   ./install.sh --auto   # 자동 모드 (Claude Code 등에서 실행)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS_FILE="$HOME/.claude/settings.json"
CLAUDE_JSON="$HOME/.claude.json"
PLIST_NAME="com.claude.session-dashboard"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PORT=18080

# --auto 플래그 감지
AUTO_MODE=false
if [ "${1:-}" = "--auto" ]; then
    AUTO_MODE=true
fi

# 인터랙티브 입력 헬퍼 (--auto 모드에서는 기본값 사용)
ask() {
    local prompt="$1"
    local default="$2"
    if [ "$AUTO_MODE" = true ]; then
        echo "$default"
        return
    fi
    read -p "$prompt" answer
    echo "${answer:-$default}"
}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Claude Code Session Dashboard — Installer   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

if [ "$AUTO_MODE" = true ]; then
    echo "  (자동 모드로 실행 중 — 모든 선택을 기본값으로 진행합니다)"
    echo ""
fi

# ─── 사전 확인 ───

# macOS 확인
if [ "$(uname)" != "Darwin" ]; then
    echo "❌ 이 도구는 macOS 전용입니다 (LaunchAgent, Terminal.app 연동)."
    echo "   세션 뷰어만 사용하려면 수동으로 실행하세요:"
    echo "   python3 convert_session.py && python3 active_server.py"
    exit 1
fi

# Python 3 확인
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3이 필요합니다."
    echo "   Homebrew: brew install python3"
    echo "   또는: https://www.python.org/downloads/"
    exit 1
fi

# Claude Code 설치 확인
if [ ! -d "$HOME/.claude" ]; then
    echo "❌ Claude Code가 설치되어 있지 않은 것 같습니다 (~/.claude 없음)."
    echo "   https://claude.ai/code 에서 설치 후 다시 시도해주세요."
    exit 1
fi

# 세션 존재 확인
PROJECTS_BASE="$HOME/.claude/projects"
if [ ! -d "$PROJECTS_BASE" ]; then
    echo "❌ Claude Code 세션 디렉토리를 찾을 수 없습니다: $PROJECTS_BASE"
    echo "   Claude Code를 한 번 이상 사용한 후 다시 시도해주세요."
    exit 1
fi

SESSION_COUNT=$(find "$PROJECTS_BASE" -name "*.jsonl" -not -name "agent-*" 2>/dev/null | wc -l | tr -d ' ')

if [ "$SESSION_COUNT" -eq 0 ]; then
    echo "⚠ 세션 로그 파일이 없습니다. Claude Code로 대화를 한 번 이상 한 후 다시 실행해주세요."
    exit 1
fi

# LaunchAgents 디렉토리 확인
if [ ! -d "$HOME/Library/LaunchAgents" ]; then
    mkdir -p "$HOME/Library/LaunchAgents"
fi

echo "✓ macOS $(sw_vers -productVersion 2>/dev/null || echo '')"
echo "✓ Python 3: $(python3 --version 2>&1 | awk '{print $2}')"
echo "✓ Claude Code 세션: ${SESSION_COUNT}개 발견"
echo "✓ 설치 경로: $SCRIPT_DIR"

# 포트 충돌 확인
if lsof -i :${PORT} >/dev/null 2>&1; then
    EXISTING_PID=$(lsof -ti :${PORT} 2>/dev/null | head -1)
    EXISTING_CMD=$(ps -p "$EXISTING_PID" -o comm= 2>/dev/null || echo "unknown")
    echo ""
    echo "⚠ 포트 ${PORT}이 이미 사용 중입니다 (PID: ${EXISTING_PID}, ${EXISTING_CMD})"
    echo "  기존 대시보드 서버라면 자동으로 교체합니다."
    echo "  다른 프로세스라면 config.json에서 port를 변경하세요."
    CONFIRM=$(ask "  계속 진행할까요? (y/N): " "y")
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "  설치를 취소합니다."
        exit 0
    fi
fi
echo ""

# ─── Step 1: 선택 설정 ───

echo "── Step 1/5: 설정"
echo ""

# --- 1a. ANTHROPIC_API_KEY ---
SAVED_API_KEY=""

echo "📌 AI 자동 요약 (선택)"
echo "   Anthropic API 키를 설정하면 세션 제목이 AI로 자동 요약됩니다."
echo "   없으면 첫 메시지가 제목으로 사용됩니다."
echo ""

if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "  ✓ ANTHROPIC_API_KEY가 이미 환경변수에 설정되어 있습니다."
    SAVED_API_KEY="$ANTHROPIC_API_KEY"
else
    INPUT_API_KEY=$(ask "  Anthropic API 키 입력 (Enter로 건너뛰기): " "")
    if [ -n "$INPUT_API_KEY" ]; then
        export ANTHROPIC_API_KEY="$INPUT_API_KEY"
        SAVED_API_KEY="$INPUT_API_KEY"

        # 셸 프로파일에 영구 저장
        SHELL_PROFILE=""
        if [ -f "$HOME/.zshrc" ]; then
            SHELL_PROFILE="$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then
            SHELL_PROFILE="$HOME/.bashrc"
        elif [ -f "$HOME/.bash_profile" ]; then
            SHELL_PROFILE="$HOME/.bash_profile"
        fi

        if [ -n "$SHELL_PROFILE" ]; then
            if ! grep -q "ANTHROPIC_API_KEY" "$SHELL_PROFILE" 2>/dev/null; then
                echo "" >> "$SHELL_PROFILE"
                echo "# Claude Code Session Dashboard — AI 자동 요약" >> "$SHELL_PROFILE"
                echo "export ANTHROPIC_API_KEY=\"${INPUT_API_KEY}\"" >> "$SHELL_PROFILE"
                echo "  ✓ API 키를 ${SHELL_PROFILE}에 저장했습니다."
            else
                echo "  ✓ API 키가 이미 ${SHELL_PROFILE}에 있습니다. 현재 세션에만 적용합니다."
            fi
        else
            echo "  ⚠ 셸 프로파일을 찾을 수 없습니다. 현재 세션에만 적용됩니다."
        fi
    else
        echo "  → 건너뜁니다. 나중에 설정하려면:"
        echo "    export ANTHROPIC_API_KEY=sk-ant-..."
        echo "    python3 ${SCRIPT_DIR}/convert_session.py --force"
    fi
fi
echo ""

# --- 1b. Trust dialog 스킵 ---
echo "📌 Trust dialog 스킵 (권장)"
echo "   대시보드에서 새 세션을 시작할 때 'trust this folder' 확인창이 뜨면"
echo "   세션이 자동으로 진행되지 않습니다."
echo ""

TRUST_CONFIGURED=false

# 현재 상태 확인
HAS_TRUST="no"
HAS_SKIP="no"

if [ -f "$CLAUDE_JSON" ]; then
    HAS_TRUST=$(python3 -c "
import json
try:
    with open('$CLAUDE_JSON') as f:
        d = json.load(f)
    print('yes' if d.get('hasTrustDialogAccepted') else 'no')
except: print('no')
" 2>/dev/null)
fi

if [ -f "$SETTINGS_FILE" ]; then
    HAS_SKIP=$(python3 -c "
import json
try:
    with open('$SETTINGS_FILE') as f:
        d = json.load(f)
    print('yes' if d.get('skipDangerousModePermissionPrompt') else 'no')
except: print('no')
" 2>/dev/null)
fi

if [ "$HAS_TRUST" = "yes" ] && [ "$HAS_SKIP" = "yes" ]; then
    echo "  ✓ Trust dialog 스킵이 이미 설정되어 있습니다."
    TRUST_CONFIGURED=true
else
    TRUST_CONFIRM=$(ask "  Trust dialog을 자동으로 건너뛸까요? (Y/n): " "Y")
    if [ "$TRUST_CONFIRM" != "n" ] && [ "$TRUST_CONFIRM" != "N" ]; then
        # ~/.claude.json 설정
        if [ "$HAS_TRUST" != "yes" ]; then
            if [ -f "$CLAUDE_JSON" ]; then
                python3 -c "
import json
try:
    with open('$CLAUDE_JSON') as f:
        d = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    d = {}
d['hasTrustDialogAccepted'] = True
with open('$CLAUDE_JSON', 'w') as f:
    json.dump(d, f, indent=2)
"
            else
                echo '{"hasTrustDialogAccepted": true}' > "$CLAUDE_JSON"
            fi
        fi

        # settings.json 설정
        if [ ! -f "$SETTINGS_FILE" ]; then
            mkdir -p "$(dirname "$SETTINGS_FILE")"
            echo '{}' > "$SETTINGS_FILE"
        fi

        if [ "$HAS_SKIP" != "yes" ]; then
            python3 -c "
import json
try:
    with open('$SETTINGS_FILE') as f:
        d = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    d = {}
d['skipDangerousModePermissionPrompt'] = True
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
"
        fi

        echo "  ✓ Trust dialog 스킵 설정 완료"
        TRUST_CONFIGURED=true
    else
        echo "  → 건너뜁니다."
    fi
fi
echo ""

# --- 1c. 외부 접속 안내 ---
echo "📌 외부 접속 (폰/노트북에서 접속하기)"
echo "   이 대시보드의 핵심 기능은 외부 기기에서의 원격 접속입니다."
echo "   같은 Wi-Fi가 아닌 외부에서 접속하려면 VPN이 필요합니다."
echo ""

TS_IP=""
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "")

if command -v tailscale &>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "")
    if [ -n "$TS_IP" ]; then
        echo "  ✓ Tailscale 감지됨: ${TS_IP}"
        echo "    외부에서 접속 주소: http://${TS_IP}:${PORT}"
    else
        echo "  ⚠ Tailscale이 설치되어 있지만 연결되지 않았습니다."
        echo "    tailscale up 으로 연결 후 외부에서 접속할 수 있습니다."
    fi
else
    if [ -n "$LOCAL_IP" ]; then
        echo "  같은 네트워크에서의 접속: http://${LOCAL_IP}:${PORT}"
    fi
    echo ""
    echo "  외부(카페, 이동 중 등)에서도 접속하려면 Tailscale(무료 VPN)을 추천합니다:"
    echo "    1. https://tailscale.com 에서 계정 생성"
    echo "    2. 이 맥과 폰/노트북 모두에 Tailscale 설치"
    echo "    3. 양쪽에서 로그인하면 자동으로 VPN 연결"
    echo "    4. Tailscale IP로 어디서든 접속 가능"
fi
echo ""

# ─── Step 2: 세션 변환 ───

echo "── Step 2/5: 세션을 HTML로 변환 중..."
if ! python3 "$SCRIPT_DIR/convert_session.py" --force; then
    echo "❌ 세션 변환에 실패했습니다."
    echo "   python3 $SCRIPT_DIR/convert_session.py --force 를 직접 실행해보세요."
    exit 1
fi
echo ""

# ─── Step 3: Stop Hook 등록 ───

echo "── Step 3/5: Claude Code Stop hook 등록..."

HOOK_COMMAND="python3 ${SCRIPT_DIR}/convert_session.py"

# settings.json이 없으면 생성
if [ ! -f "$SETTINGS_FILE" ]; then
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    echo '{}' > "$SETTINGS_FILE"
fi

# Python으로 안전하게 JSON 병합
python3 << PYEOF
import json, sys

settings_path = "$SETTINGS_FILE"
hook_command = "$HOOK_COMMAND"

try:
    with open(settings_path, 'r', encoding='utf-8') as f:
        settings = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    settings = {}

# hooks.Stop 배열 가져오기 (없으면 생성)
hooks = settings.setdefault('hooks', {})
stop_hooks = hooks.setdefault('Stop', [])

# 이미 등록되어 있는지 확인
already_exists = False
for entry in stop_hooks:
    if isinstance(entry, dict) and 'hooks' in entry:
        for h in entry['hooks']:
            if h.get('command', '') == hook_command:
                already_exists = True
                break
    elif isinstance(entry, dict) and entry.get('command', '') == hook_command:
        already_exists = True
    if already_exists:
        break

if already_exists:
    print("  이미 등록되어 있습니다. 건너뜁니다.")
else:
    if stop_hooks and isinstance(stop_hooks[0], dict) and 'hooks' in stop_hooks[0]:
        new_entry = {"hooks": [{"type": "command", "command": hook_command, "timeout": 30}]}
    else:
        new_entry = {"type": "command", "command": hook_command, "timeout": 30}

    stop_hooks.insert(0, new_entry)

    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print("  ✓ Stop hook 등록 완료")
PYEOF
echo ""

# ─── Step 4: LaunchAgent 등록 ───

echo "── Step 4/5: LaunchAgent 등록 (서버 자동 시작)..."

# 기존 것이 있으면 먼저 제거
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    sleep 1
fi

# API 키가 있으면 LaunchAgent 환경변수에 포함
ENV_SECTION=""
EFFECTIVE_API_KEY="${SAVED_API_KEY:-${ANTHROPIC_API_KEY:-}}"
if [ -n "$EFFECTIVE_API_KEY" ]; then
    ENV_SECTION="    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>${EFFECTIVE_API_KEY}</string>
    </dict>"
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
${ENV_SECTION}
</dict>
</plist>
PLISTEOF

if ! launchctl load "$PLIST_PATH" 2>/dev/null; then
    echo "  ⚠ LaunchAgent 로드에 실패했습니다."
    echo "    수동으로 서버를 시작하세요: python3 ${SCRIPT_DIR}/active_server.py"
else
    sleep 2
    if curl -s "http://localhost:${PORT}/whoami" >/dev/null 2>&1; then
        echo "  ✓ 서버 시작됨: http://localhost:${PORT}"
    else
        echo "  ⚠ 서버가 아직 시작되지 않았을 수 있습니다."
        echo "    로그 확인: cat ${SCRIPT_DIR}/server.log"
    fi
fi
echo ""

# ─── Step 5: 완료 ───

echo "── Step 5/5: 브라우저 열기..."
open "http://localhost:${PORT}" 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ 설치 완료!                                       ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
echo "║  대시보드: http://localhost:${PORT}                    ║"
echo "║                                                      ║"
echo "║  ✓ 서버는 로그인 시 자동으로 시작됩니다               ║"
echo "║  ✓ 세션 종료 시 HTML이 자동으로 갱신됩니다            ║"

if [ -n "$EFFECTIVE_API_KEY" ]; then
echo "║  ✓ AI 자동 요약 활성화됨                              ║"
fi

if [ "$TRUST_CONFIGURED" = true ]; then
echo "║  ✓ Trust dialog 자동 스킵 설정됨                      ║"
fi

echo "║                                                      ║"
echo "║  제거: ./uninstall.sh                                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# 접속 주소 안내
echo "💡 다른 기기에서 접속:"
if [ -n "$TS_IP" ]; then
    echo "   외부 (VPN):     http://${TS_IP}:${PORT}"
fi
if [ -n "$LOCAL_IP" ]; then
    echo "   같은 네트워크:  http://${LOCAL_IP}:${PORT}"
fi
echo ""
