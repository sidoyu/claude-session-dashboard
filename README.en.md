# Claude Code Session Dashboard

[한국어](README.md)

A web-based dashboard for browsing, searching, and managing your [Claude Code](https://claude.ai/code) conversation sessions.

Claude Code stores all conversation logs as JSONL files, but there's no built-in way to browse them in a readable format. This tool converts those logs into a clean, searchable web dashboard.

## Why I built this

I use Claude Code extensively for my daily work. After accumulating hundreds of sessions, I needed a way to:

- **Find past conversations** — "What was that session where I set up the monitoring script?"
- **Browse sessions from my phone** — Review conversations on the go, without opening a terminal
- **Manage active sessions** — Start, stop, and resume sessions from a web UI
- **Get readable conversation logs** — JSONL files are not fun to read

## Features

| Feature | Description |
|---------|-------------|
| **JSONL → HTML conversion** | Converts Claude Code session logs into markdown-rendered HTML pages |
| **Session dashboard** | Lists all sessions with titles, timestamps, duration, and message counts |
| **Full-text search** | Server-side search across all conversation history |
| **Auto-summarization** | Generates session titles using Claude Haiku API (optional) |
| **Session control** | Start, stop, and resume sessions from the web UI (macOS only) |
| **Dark mode** | Automatic light/dark theme |
| **Mobile-friendly** | Responsive layout with pull-to-refresh |
| **Export** | Download any session as a self-contained HTML file |
| **i18n** | Korean (default) and English UI |

## How is this different?

There are several great Claude Code log viewers ([clear-code](https://github.com/chatgptprojects/clear-code), [sniffly](https://github.com/chiphuyen/sniffly), [cclogviewer](https://github.com/Brads3290/cclogviewer), etc.). This project focuses on a different use case:

| | Most viewers | This project |
|---|---|---|
| **Access** | Desktop only | Phone, tablet, any browser |
| **Session control** | Read-only | Start, stop, resume from web UI |
| **Search** | Client-side or none | Server-side full-text JSONL search |
| **Titles** | Filename or first message | AI-generated summaries via Claude Haiku |
| **Multi-device** | Single machine | Primary + proxy for VPN setups |
| **Dependencies** | Node.js, Go, or npm | Python 3 stdlib only — zero dependencies |

## Quick Start

### Requirements

- **Python 3.8+** (stdlib only, no pip packages)
- **Claude Code** installed (session logs needed)
- **macOS** (for session control; viewer works on any OS)

### 1. Clone

```bash
git clone https://github.com/sidoyu/claude-session-dashboard.git
cd claude-session-dashboard
```

### 2. Switch to English UI

```bash
cp config.example.json config.json
# Edit config.json and set "lang": "en"
```

### 3. Convert sessions

```bash
python3 convert_session.py
```

### 4. Start server

```bash
python3 active_server.py
```

Open `http://localhost:18080`.

## Configuration

### config.json

```json
{
  "port": 18080,
  "lang": "en",
  "claude_path": "~/.local/bin/claude",
  "machine_role": "auto",
  "proxy_target_ip": ""
}
```

| Field | Description | Default |
|-------|-------------|---------|
| `port` | Server port | `18080` |
| `lang` | UI language (`"ko"` or `"en"`) | `"ko"` |
| `claude_path` | Path to `claude` CLI | `~/.local/bin/claude` |
| `machine_role` | `"auto"`, `"primary"`, or `"proxy"` | `"auto"` |
| `proxy_target_ip` | Primary server IP (multi-machine only) | `""` |

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | For auto-summarization (optional) | _(none)_ |
| `CLAUDE_DASHBOARD_LANG` | UI language override | `ko` |
| `CLAUDE_DASHBOARD_TZ` | Timezone offset from UTC | `9` (KST) |
| `CLAUDE_PROJECTS_DIR` | Override projects directory | _(auto-detected)_ |

### Auto-convert on session end

Add a stop hook in `~/.claude/settings.json`:

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

## How it works

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

## Limitations

- **Session control is macOS-only** (AppleScript). Viewer and search work on any OS.
- **No authentication** — run on trusted networks or behind a VPN.
- **CDN dependency** — markdown rendering uses CDN. Export strips CDN for offline.
- **Single-user** — personal use, not team access.

## License

MIT
