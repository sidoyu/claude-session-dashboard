# Claude Code Session Dashboard

[English](README.en.md)

맥미니(또는 데스크탑) 한 대에서 [Claude Code](https://claude.ai/code)를 돌리고, 밖에서 폰이나 노트북으로 세션을 모니터링하고 제어하는 웹 대시보드입니다.

## 이게 왜 필요한가

Claude Code는 터미널 기반 도구입니다. 집이나 사무실의 데스크탑에서 세션을 돌려놓고 외출하면, 그 세션이 어떻게 됐는지 확인할 방법이 마땅치 않습니다.

**내가 겪은 불편:**

- 맥미니에서 Claude Code 세션을 걸어놓고 나갔는데, 밖에서 진행 상황을 볼 수가 없음
- 폰에서 "아까 그 세션 결과 어떻게 됐지?" 확인하려면, 집에 돌아와서 터미널을 열어야 함
- 세션이 끝났으면 새 작업을 시작하고 싶은데, 원격으로 세션을 시작할 방법이 없음
- 세션이 수백 개 쌓이면 "예전에 뭐 했더라?" 찾는 게 불가능 — JSONL 파일을 직접 뒤질 수는 없으니까

**이 도구가 해결하는 것:**

```
┌─────────────┐                    ┌──────────────┐
│ 밖에서       │   VPN / 같은 망    │  집 맥미니    │
│ 폰·패드·노트북│ ──────────────────▶│  Claude Code  │
│ (브라우저)    │   웹 대시보드 접속  │  실행 중      │
└─────────────┘                    └──────────────┘

 ✓ 세션 대화 기록 열람 (마크다운 렌더링)
 ✓ 세션 시작 / 중지 / 재개
 ✓ 전체 대화 내용 검색
 ✓ AI 자동 제목 요약
```

데스크탑 한 대를 Claude Code 메인 머신으로 쓰고, 이동 중에는 포터블 기기로 원격 제어하는 워크플로우를 위한 도구입니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| **JSONL → HTML 변환** | Claude Code 세션 로그를 마크다운 렌더링된 HTML 페이지로 변환 |
| **세션 대시보드** | 제목, 시간, 소요시간, 메시지 수와 함께 전체 세션 목록 표시 |
| **전문 검색** | 서버사이드에서 전체 대화 기록을 검색 |
| **자동 요약** | Claude Haiku API로 세션 제목 자동 생성 (선택, API 키 필요) |
| **세션 제어** | 웹 UI에서 세션 시작/중지/재개 (macOS만 지원) |
| **다크 모드** | 시스템 설정에 따라 자동 전환 |
| **모바일 대응** | 반응형 레이아웃 + 당겨서 새로고침 (홈 화면 웹앱) |
| **내보내기** | 세션을 독립 실행 가능한 HTML 파일로 다운로드 |
| **세션 숨기기** | 목록에서 보고 싶지 않은 세션 숨김 처리 |

## 다른 프로젝트와 뭐가 다른가?

Claude Code 로그 뷰어는 이미 여러 좋은 프로젝트가 있습니다 ([clear-code](https://github.com/chatgptprojects/clear-code), [sniffly](https://github.com/chiphuyen/sniffly), [cclogviewer](https://github.com/Brads3290/cclogviewer) 등). 이 프로젝트는 다른 유스케이스에 초점을 맞추고 있습니다:

| | 대부분의 뷰어 | 이 프로젝트 |
|---|---|---|
| **접근성** | 데스크탑에서만 | 폰, 태블릿, 어떤 브라우저든 (로컬 서버 경유) |
| **세션 제어** | 읽기 전용 | 웹 UI에서 시작/중지/재개 |
| **검색** | 클라이언트사이드 또는 없음 | 서버사이드 JSONL 전문 검색 |
| **제목** | 파일명 또는 첫 메시지 | Claude Haiku로 AI 자동 요약 |
| **멀티 기기** | 단일 머신 | 메인 서버 + 프록시 구조 (VPN 연동) |
| **의존성** | Node.js, Go, npm install 등 | Python 3 표준 라이브러리만 — 의존성 제로 |

단순히 로그만 보고 싶다면 [cclogviewer](https://github.com/Brads3290/cclogviewer)나 [clear-code](https://github.com/chatgptprojects/clear-code)가 좋은 선택입니다. 이 프로젝트는 **폰에서도 접근 가능한 상시 대시보드**가 필요하고, **세션을 원격으로 제어**하고 싶은 경우에 적합합니다.

## 스크린샷

### 데스크탑

**대시보드** — 세션 목록, 활성/비활성 상태, 시작/중지 제어

![Desktop Dashboard](screenshots/desktop-dashboard.png)

**세션 상세** — 마크다운 렌더링, 구문 강조, 도구 사용 내역

![Desktop Session](screenshots/desktop-session.png)

**검색** — 서버사이드 전문 검색, 하이라이트 스니펫

![Desktop Search](screenshots/desktop-search.png)

### 모바일 (iPhone)

폰에서 접속한 모습. 밖에서도 세션을 확인하고 제어할 수 있습니다.

<p float="left">
  <img src="screenshots/mobile-dashboard.png" width="250" />
  <img src="screenshots/mobile-session.png" width="250" />
  <img src="screenshots/mobile-search.png" width="250" />
</p>

## 빠른 시작

### 필요 사항

- **Python 3.8 이상** (pip 패키지 불필요 — 표준 라이브러리만 사용)
- **Claude Code**가 설치되어 있고 사용한 적이 있어야 합니다 (세션 로그 파일 필요)
- **macOS** (세션 제어 기능. 뷰어와 검색은 모든 OS에서 동작)

### 1. 클론

```bash
git clone https://github.com/sidoyu/claude-session-dashboard.git
cd claude-session-dashboard
```

### 2. 세션을 HTML로 변환

```bash
python3 convert_session.py
```

이 명령은:
- Claude Code 세션 디렉토리(`~/.claude/projects/`)를 자동 감지합니다
- 모든 JSONL 세션 로그를 HTML 파일로 변환합니다
- `index.html` 대시보드와 `search.html` 검색 페이지를 생성합니다

### 3. 서버 시작

```bash
python3 active_server.py
```

브라우저에서 `http://localhost:18080`을 열면 됩니다.

끝! 이제 모든 Claude Code 세션을 웹에서 둘러볼 수 있습니다.

## 설정

### 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | 자동 요약을 위한 Anthropic API 키 (선택) | _(없음 — 첫 메시지를 제목으로 사용)_ |
| `CLAUDE_DASHBOARD_LANG` | UI 언어 (`ko` 또는 `en`) | `ko` |
| `CLAUDE_DASHBOARD_TZ` | UTC 기준 시간대 오프셋 (예: KST는 `9`, EST는 `-5`) | `9` (KST) |
| `CLAUDE_PROJECTS_DIR` | Claude Code 프로젝트 디렉토리 경로 지정 | _(자동 감지)_ |
| `CLAUDE_DASHBOARD_DIR` | 생성된 HTML 출력 디렉토리 | _(스크립트와 같은 디렉토리)_ |

### config.json (선택)

예시 설정 파일을 복사해서 수정하세요:

```bash
cp config.example.json config.json
```

```json
{
  "port": 18080,
  "lang": "ko",
  "claude_path": "~/.local/bin/claude",
  "machine_role": "auto",
  "proxy_target_ip": "",
  "remote_server_ip": ""
}
```

| 필드 | 설명 | 기본값 |
|------|------|--------|
| `port` | 서버 포트 | `18080` |
| `lang` | UI 언어 (`"ko"` 또는 `"en"`) | `"ko"` |
| `claude_path` | `claude` CLI 바이너리 경로 | `~/.local/bin/claude` |
| `machine_role` | `"auto"`, `"primary"`, `"proxy"` 중 선택 | `"auto"` |
| `proxy_target_ip` | 메인 서버의 IP (멀티 머신 구성 시에만 사용) | `""` |

> **참고:** `config.json`은 `.gitignore`에 포함되어 있어서 개인 설정이 커밋되지 않습니다.

### 자동 요약 (선택)

`ANTHROPIC_API_KEY`를 설정하면 Claude Haiku로 세션별 한 줄 제목을 자동 생성합니다 (예: "네이버 카페 모니터링 자동화 구현"). 설정하지 않으면 첫 사용자 메시지가 제목이 됩니다.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 convert_session.py
```

## 사용법

### 세션 변환

```bash
# 전체 변환 (증분 처리 — 변경된 세션만)
python3 convert_session.py

# 전체 강제 재변환 (템플릿 수정 후 등)
python3 convert_session.py --force

# 특정 세션만 변환
python3 convert_session.py <session-id>

# 세션 제목 변경
python3 convert_session.py --rename <session-id> "새 제목"
```

### 상시 서비스로 실행 (macOS)

로그인 시 서버가 자동으로 시작되도록 LaunchAgent를 만듭니다:

```bash
cat > ~/Library/LaunchAgents/com.claude.session-dashboard.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.session-dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/claude-session-dashboard/active_server.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/path/to/claude-session-dashboard</string>
</dict>
</plist>
EOF
```

`/path/to/claude-session-dashboard`를 실제 경로로 바꾼 후:

```bash
launchctl load ~/Library/LaunchAgents/com.claude.session-dashboard.plist
```

### 세션 종료 시 자동 변환 (Claude Code hook)

Claude 세션이 끝날 때 자동으로 HTML을 재생성하도록 Stop hook을 추가합니다.

`~/.claude/settings.json`을 편집하세요:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "python3 /path/to/claude-session-dashboard/convert_session.py",
        "timeout": 30
      }
    ]
  }
}
```

### 멀티 머신 구성 (고급)

Tailscale 등 VPN으로 연결된 여러 대의 Mac에서 Claude Code를 사용하는 경우:

1. **메인 머신** (Claude Code를 실행하는 곳): 기본 설정 그대로 사용
2. **보조 머신**: `config.json`에 다음과 같이 설정:

```json
{
  "machine_role": "proxy",
  "proxy_target_ip": "100.x.x.x"
}
```

보조 머신은 모든 요청을 메인 서버로 프록시합니다.

## 동작 원리

```
~/.claude/projects/         convert_session.py        active_server.py
┌──────────────────┐       ┌──────────────────┐      ┌──────────────────┐
│ session-abc.jsonl │──────▶│ session-abc.html │──────▶│  localhost:18080 │
│ session-def.jsonl │──────▶│ session-def.html │      │                  │
│ ...               │       │ index.html       │      │  /active         │
└──────────────────┘       │ search.html      │      │  /search?q=      │
                            └──────────────────┘      │  /start/<sid>    │
                                                      └──────────────────┘
```

1. **Claude Code**가 대화 기록을 `~/.claude/projects/`에 JSONL 파일로 저장
2. **convert_session.py**가 JSONL 파일을 읽어서 HTML 페이지를 생성:
   - 마크다운 렌더링 ([marked.js](https://marked.js.org/) CDN)
   - 구문 강조 ([highlight.js](https://highlightjs.org/) CDN)
   - 도구 사용 내역을 접을 수 있는 섹션으로 표시
   - 시스템 프롬프트 및 내부 태그 자동 제거
3. **active_server.py**가 HTML 파일을 서빙하고 다음 API를 제공:
   - 활성 세션 감지 (`ps aux` 기반)
   - 세션 시작/중지 (macOS Terminal.app AppleScript)
   - JSONL 파일 전문 검색
   - 세션 제목 관리

## 한계

- **세션 제어(시작/중지/재개)는 macOS 전용** — Terminal.app을 AppleScript로 제어합니다. 뷰어와 검색은 모든 OS에서 동작합니다.
- **인증 없음** — 서버가 `0.0.0.0`에 바인딩되며 인증이 없습니다. 신뢰할 수 있는 네트워크나 VPN 안에서만 사용하세요.
- **CDN 의존** — 세션 상세 페이지에서 marked.js와 highlight.js를 CDN에서 로드합니다. 내보내기 기능은 오프라인 열람을 위해 CDN을 제거합니다.
- **개인 사용 전용** — 팀 공유용이 아닌 1인 사용 도구입니다.
- **기본 시간대 KST** — 타임스탬프가 기본적으로 UTC+9(KST)입니다. `CLAUDE_DASHBOARD_TZ` 환경 변수로 변경 가능합니다.

## 파일 구조

```
claude-session-dashboard/
├── active_server.py        # HTTP 서버 + 세션 제어 API
├── convert_session.py      # JSONL → HTML 변환기
├── sw.js                   # Service Worker (브라우저 캐싱)
├── config.example.json     # 설정 파일 예시
├── .gitignore              # 생성 파일, 데이터, config 제외
└── README.md
```

자동 생성되는 파일 (repo에 포함되지 않음):
```
├── index.html              # 대시보드 페이지
├── search.html             # 검색 페이지
├── <session-id>.html       # 개별 세션 페이지
├── summaries.json          # 세션 제목 요약 캐시
├── hidden_sessions.json    # 숨긴 세션 ID 목록
└── config.json             # 개인 설정 파일
```

## 라이선스

MIT
