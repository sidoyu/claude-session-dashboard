# Claude Code Session Dashboard

A web-based dashboard for browsing, searching, and managing your [Claude Code](https://claude.ai/code) conversation sessions.

Claude Code stores all conversation logs as JSONL files, but there's no built-in way to browse them in a readable format. This tool converts those logs into a clean, searchable web dashboard.

## Why I built this

I use Claude Code extensively for my daily work. After accumulating hundreds of sessions, I needed a way to:

- **Find past conversations** — "What was that session where I set up the monitoring script?"
- **Browse sessions from my phone** — Review conversations on the go, without opening a terminal
- **Manage active sessions** — Start, stop, and resume sessions from a web UI
- **Get readable conversation logs** — JSONL files are not fun to read

## What it does

| Feature | Description |
|---------|-------------|
| **JSONL to HTML conversion** | Converts Claude Code session logs into nicely formatted, markdown-rendered HTML pages |
| **Session dashboard** | Lists all sessions with titles, timestamps, duration, and message counts |
| **Full-text search** | Server-side search across all your conversation history |
| **Auto-summarization** | Generates session titles using Claude Haiku API (optional, requires API key) |
| **Session control** | Start, stop, and resume sessions from the web UI (macOS only) |
| **Dark mode** | Automatic light/dark theme based on system preference |
| **Mobile-friendly** | Responsive layout with pull-to-refresh for home screen web apps |
| **Export** | Download any session as a self-contained HTML file |
| **Hide sessions** | Hide sessions you don't want cluttering the list |

## Screenshots

After running the dashboard, you'll see:

- **Dashboard** — A table listing all your sessions, sorted by recency
- **Session detail** — Full conversation with markdown rendering, syntax highlighting, and tool use details
- **Search** — Real-time search with highlighted snippets

## Quick Start

### Requirements

- **Python 3.8+** (no pip packages needed — stdlib only)
- **Claude Code** installed and used (so you have session logs)
- **macOS** (for session control features; the viewer works on any OS)

### 1. Clone and set up

```bash
git clone https://github.com/sidoyu/claude-session-dashboard.git
cd claude-session-dashboard
```

### 2. Convert your sessions to HTML

```bash
python3 convert_session.py
```

This will:
- Auto-detect your Claude Code session directory (`~/.claude/projects/`)
- Convert all JSONL session logs to HTML files
- Generate an `index.html` dashboard and `search.html` page

### 3. Start the server

```bash
python3 active_server.py
```

Open `http://localhost:18080` in your browser.

That's it! You now have a browsable dashboard of all your Claude Code sessions.

## Configuration

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key for auto-summarization (optional) | _(none — sessions use first message as title)_ |
| `CLAUDE_DASHBOARD_TZ` | Timezone offset in hours from UTC (e.g., `9` for KST, `-5` for EST) | `9` |
| `CLAUDE_PROJECTS_DIR` | Override Claude Code projects directory | _(auto-detected)_ |
| `CLAUDE_DASHBOARD_DIR` | Override output directory for generated HTML | _(same as script directory)_ |

### config.json (optional)

Copy the example config and edit as needed:

```bash
cp config.example.json config.json
```

```json
{
  "port": 18080,
  "claude_path": "~/.local/bin/claude",
  "machine_role": "auto",
  "proxy_target_ip": "",
  "remote_server_ip": ""
}
```

| Field | Description | Default |
|-------|-------------|---------|
| `port` | Server port | `18080` |
| `claude_path` | Path to `claude` CLI binary | `~/.local/bin/claude` |
| `machine_role` | `"auto"`, `"primary"`, or `"proxy"` | `"auto"` |
| `proxy_target_ip` | IP of the primary server (only for multi-machine setup) | `""` |

> **Note:** `config.json` is in `.gitignore` — your personal settings won't be committed.

### Auto-summarization (optional)

If you set `ANTHROPIC_API_KEY`, the converter will call Claude Haiku to generate short titles for each session (e.g., "Set up Naver cafe monitoring"). Without it, sessions are titled with the first user message.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 convert_session.py
```

## Usage

### Convert sessions

```bash
# Convert all (incremental — only changed sessions)
python3 convert_session.py

# Force reconvert everything (e.g., after template changes)
python3 convert_session.py --force

# Convert a specific session
python3 convert_session.py <session-id>

# Rename a session
python3 convert_session.py --rename <session-id> "New title"
```

### Run as a persistent service (macOS)

To have the server start automatically on login, create a LaunchAgent:

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

Replace `/path/to/claude-session-dashboard` with the actual path, then:

```bash
launchctl load ~/Library/LaunchAgents/com.claude.session-dashboard.plist
```

### Auto-convert on session end (Claude Code hook)

Add a stop hook so sessions are converted automatically when Claude finishes:

Edit `~/.claude/settings.json`:

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

### Multi-machine setup (advanced)

If you run Claude Code on multiple machines connected via Tailscale or similar VPN:

1. **Primary machine** (where Claude Code runs): Use default config
2. **Secondary machine**: Create `config.json` with:

```json
{
  "machine_role": "proxy",
  "proxy_target_ip": "100.x.x.x"
}
```

The secondary machine will proxy all requests to the primary.

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

1. **Claude Code** stores conversation logs as JSONL files in `~/.claude/projects/`
2. **convert_session.py** reads those JSONL files and generates HTML pages with:
   - Markdown rendering (via [marked.js](https://marked.js.org/) CDN)
   - Syntax highlighting (via [highlight.js](https://highlightjs.org/) CDN)
   - Tool use details in collapsible sections
   - System prompt and internal tags stripped out
3. **active_server.py** serves the HTML files and provides APIs for:
   - Active session detection (via `ps aux`)
   - Session start/stop (via Terminal.app AppleScript on macOS)
   - Full-text search across JSONL files
   - Session title management

## Limitations

- **Session control (start/stop/resume) is macOS-only** — it uses AppleScript to control Terminal.app. The viewer and search work on any OS.
- **No authentication** — the server binds to `0.0.0.0` with no auth. Only run it on a trusted network or behind a VPN.
- **CDN dependency** — session detail pages load marked.js and highlight.js from CDN for markdown rendering. The export feature strips these for offline viewing.
- **Single-user** — designed for personal use, not shared team access.
- **KST default timezone** — timestamps default to UTC+9 (KST). Change via `CLAUDE_DASHBOARD_TZ` environment variable.

## File structure

```
claude-session-dashboard/
├── active_server.py        # HTTP server with session control APIs
├── convert_session.py      # JSONL → HTML converter
├── sw.js                   # Service Worker for browser caching
├── config.example.json     # Example configuration
├── .gitignore              # Excludes generated HTML, data files, config
└── README.md
```

Generated files (not in repo):
```
├── index.html              # Dashboard page
├── search.html             # Search page
├── <session-id>.html       # Individual session pages
├── summaries.json          # Cached session title summaries
├── hidden_sessions.json    # Hidden session IDs
└── config.json             # Your personal config
```

## License

MIT
