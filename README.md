# Claude Code Session Dashboard

[English](README.en.md)

## 이런 분을 위한 도구입니다

- 맥미니나 데스크탑을 **항상 켜두고** [Claude Code](https://claude.ai/code)를 돌리는 사람
- 세션을 걸어놓고 자리를 비우는 일이 많은 사람
- 밖에서 **폰이나 노트북**으로 세션 상태를 확인하고 싶은 사람
- 외출 중에도 맥미니에게 **새 작업을 시키거나**, 기존 세션을 **이어서 작업**하고 싶은 사람

항상 인터넷에 연결된 데스크탑 한 대가 Claude Code의 메인 머신이고, 이동 중에는 다른 기기에서 원격으로 모니터링하고 작업을 지시하는 워크플로우를 전제로 만들었습니다. 대시보드에서 시작하거나 재개한 세션은 `--remote-control` 플래그가 자동 적용되어 [claude.ai/code](https://claude.ai/code) 웹앱에서도 바로 접속할 수 있습니다.

## 어떤 불편을 해결하나

Claude Code는 터미널 기반 도구입니다. 데스크탑에서 세션을 돌려놓고 외출하면:

- 밖에서 **진행 상황을 볼 수가 없음** — 끝났는지, 에러났는지 알 방법이 없음
- 결과를 확인하려면 **집에 돌아와서 터미널을 열어야 함**
- 세션이 끝났으면 **새 작업을 바로 시작하고 싶은데** 원격으로 할 수가 없음
- 진행 중인 세션에 **추가 지시를 하고 싶은데** 데스크탑 앞에 없으면 불가능
- 세션이 수백 개 쌓이면 **"예전에 뭐 했더라?"** 찾는 게 불가능

이 도구는 데스크탑에 웹 서버를 띄워서, 어떤 기기의 브라우저에서든 세션을 열람하고 제어할 수 있게 해줍니다.

```
┌─────────────┐                    ┌──────────────────┐
│ 밖에서       │   VPN / 같은 망    │  집 / 사무실      │
│ 폰·패드·노트북│ ──────────────────▶│  항상 켜둔 데스크탑 │
│ (브라우저)    │   웹 대시보드 접속  │  Claude Code 실행  │
└─────────────┘                    └──────────────────┘

 ✓ 세션 대화 기록 열람 (마크다운 렌더링)
 ✓ 새 세션 시작 / 기존 세션 재개 / 중지
 ✓ 재개한 세션에 claude.ai/code로 바로 접속
 ✓ 전체 대화 내용 검색
 ✓ AI 자동 제목 요약
```

### 원격에서 작업하는 흐름

외출 중에 맥미니의 Claude Code에 작업을 시키고 싶을 때:

1. **폰/패드/노트북 브라우저**에서 대시보드(`http://맥미니IP:18080`)에 접속
2. 기존 세션의 **"활성"** 버튼을 누르거나, 하단에서 **"+ 새 세션"**으로 새 작업을 시작
3. [claude.ai/code](https://claude.ai/code) 웹앱을 열면 해당 세션에 바로 접속 가능 (`--remote-control` 자동 적용)
4. 웹앱에서 대화를 이어가며 작업 지시

> **참고:** 원격 기기에서 Claude Code CLI를 직접 실행하는 게 아닙니다. 모든 세션은 맥미니에서 실행되고, 원격 기기에서는 **claude.ai/code 웹앱** 또는 **Claude 앱의 Code 기능**을 통해 접속합니다.

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

### 설치 (한 번만)

Claude Code에게 이렇게 말하면 됩니다:

> https://github.com/sidoyu/claude-session-dashboard 이거 클론하고 `./install.sh --auto` 실행해줘

직접 실행하면 API 키, trust dialog 등을 인터랙티브하게 설정할 수 있습니다:

```bash
git clone https://github.com/sidoyu/claude-session-dashboard.git
cd claude-session-dashboard
./install.sh
```

| 모드 | 명령어 | 용도 |
|------|--------|------|
| **인터랙티브** | `./install.sh` | 사람이 직접 실행. API 키, trust dialog 등 하나씩 설정 |
| **자동** | `./install.sh --auto` | Claude Code가 실행. 기본값으로 자동 진행 |

`install.sh`가 자동으로 수행하는 것:

1. 모든 Claude Code 세션을 HTML로 변환
2. Claude Code Stop hook 등록 (세션 종료 시 자동 변환)
3. LaunchAgent 등록 (서버가 로그인 시 자동 시작, 크래시 시 재시작)
4. 브라우저에서 `http://localhost:18080` 열기

설치가 끝나면 **이후로는 아무것도 할 필요 없습니다.** 서버가 항상 떠 있고, Claude Code 세션이 끝날 때마다 HTML이 자동으로 갱신됩니다.

### 제거

```bash
./uninstall.sh
```

LaunchAgent, Stop hook, 생성된 HTML 파일을 모두 정리합니다.

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

### 수동 설정 (install.sh를 사용하지 않는 경우)

`install.sh`가 LaunchAgent와 Stop hook을 자동으로 등록합니다. 수동으로 하고 싶다면:

- **LaunchAgent**: `~/Library/LaunchAgents/com.claude.session-dashboard.plist` 직접 생성
- **Stop hook**: `~/.claude/settings.json`의 `hooks.Stop` 배열에 `python3 /path/to/convert_session.py` 추가

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
- **새 세션 시작 시 180초 타임아웃** — 대시보드에서 새 세션을 시작하면 첫 번째 프롬프트의 응답이 완료될 때까지 동기적으로 대기하며, 180초(3분) 제한이 있습니다. 원격에서 새 세션을 시작할 때는 `"안녕"` 같은 간단한 인사로 시작한 뒤, 세션이 생성되면 [claude.ai/code](https://claude.ai/code) 웹앱에서 접속하여 본격적인 작업을 진행하세요.

## 파일 구조

```
claude-session-dashboard/
├── install.sh              # 설치 스크립트 (한 번만 실행)
├── uninstall.sh            # 제거 스크립트
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
