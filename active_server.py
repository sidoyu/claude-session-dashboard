#!/usr/bin/env python3
"""
Claude Code Session Dashboard Server.

Serves the session dashboard and provides APIs for session control.

- GET /              → index.html
- GET /<file>.html   → Static HTML files
- GET /active        → Active sessions (JSON)
- GET /start/<sid>   → Start session (Terminal + claude --resume)
- GET /stop/<sid>    → Stop session
- GET /new-session   → Create new session
- GET /whoami        → Machine info (JSON)
- GET /refresh       → Run convert_session.py
- GET /hidden        → Hidden sessions list
- POST /hidden-update → Save hidden sessions
- GET /rename/<sid>  → Rename session title
- GET /search?q=     → Full-text search in JSONL files

Port: 18080 (default, configurable via config.json)
"""

import http.server
import json
import os
import socket
import subprocess
import re
import threading
import time
import urllib.parse
import urllib.request

# ─── Configuration ───

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(LOGS_DIR, "config.json")

# Default configuration
_config = {
    "port": 18080,
    "claude_path": os.path.expanduser("~/.local/bin/claude"),
    "remote_server_ip": "",       # Tailscale/VPN IP of the primary server (optional, for multi-machine setup)
    "proxy_target_ip": "",        # IP to proxy to (optional, for secondary machine)
    "machine_role": "auto",       # "auto", "primary", or "proxy"
}

# Load config from file if exists
if os.path.isfile(CONFIG_PATH):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        _config.update(json.load(f))

PORT = _config["port"]
CLAUDE_PATH = _config["claude_path"]
PROXY_TARGET_IP = _config.get("proxy_target_ip", "")

# Auto-detect PROJECTS_DIR (find the first project directory under ~/.claude/projects/)
def _find_projects_dir():
    base = os.path.expanduser("~/.claude/projects")
    if os.path.isdir(base):
        for entry in os.listdir(base):
            full = os.path.join(base, entry)
            if os.path.isdir(full) and entry.startswith("-"):
                return full
    return base

PROJECTS_DIR = _find_projects_dir()


def get_machine_role():
    """Determine if this server is the primary or proxy."""
    configured = _config.get("machine_role", "auto")
    if configured == "primary":
        return "primary"
    elif configured == "proxy":
        return "proxy"

    # Auto-detect: if proxy_target_ip is set and we're not that IP, we're a proxy
    if PROXY_TARGET_IP:
        try:
            result = subprocess.run(
                ['hostname', '-I'] if os.name != 'darwin' else ['ipconfig', 'getifaddr', 'en0'],
                capture_output=True, text=True, timeout=5
            )
            local_ip = result.stdout.strip().split()[0] if result.stdout.strip() else ''
            if local_ip != PROXY_TARGET_IP:
                return 'proxy'
        except Exception:
            pass

    return 'primary'


MACHINE_ROLE = get_machine_role()


# ─── HTTP Handler ───

class SessionHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/hidden-update':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode()
            if MACHINE_ROLE == 'primary':
                try:
                    hidden_list = json.loads(body)
                    hidden_path = os.path.join(LOGS_DIR, 'hidden_sessions.json')
                    with open(hidden_path, 'w') as f:
                        json.dump(hidden_list, f)
                    self._json_response({'status': 'ok'})
                except Exception as e:
                    self._json_response({'status': 'error', 'message': str(e)}, 400)
            else:
                self._proxy_post(f"http://{PROXY_TARGET_IP}:{PORT}/hidden-update", body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/active':
            self._json_response(get_active_sessions())

        elif path == '/whoami':
            self._json_response({'machine': MACHINE_ROLE, 'hostname': socket.gethostname()})

        elif path.startswith('/start/'):
            sid = path[7:]
            if not re.match(r'^[a-f0-9-]+$', sid):
                self._json_response({'error': 'invalid session id'}, 400)
                return
            result = start_session(sid)
            self._json_response(result)

        elif path.startswith('/stop/'):
            sid = path[6:]
            if not re.match(r'^[a-f0-9-]+$', sid):
                self._json_response({'error': 'invalid session id'}, 400)
                return
            result = stop_session(sid)
            self._json_response(result)

        elif path == '/new-session':
            params = urllib.parse.parse_qs(parsed.query)
            msg = params.get('msg', ['hi'])[0]
            result = new_session(msg)
            self._json_response(result)

        elif path == '/hidden':
            if MACHINE_ROLE == 'primary':
                filepath = os.path.join(LOGS_DIR, 'hidden_sessions.json')
                if os.path.isfile(filepath):
                    self._serve_file('hidden_sessions.json', 'application/json')
                else:
                    self._json_response([])
            else:
                self._proxy_get(f"http://{PROXY_TARGET_IP}:{PORT}/hidden")

        elif path.startswith('/rename/'):
            sid = path[8:]
            params = urllib.parse.parse_qs(parsed.query)
            title = params.get('title', [''])[0]
            if sid and title:
                if MACHINE_ROLE == 'primary':
                    self._json_response(rename_session(sid, title))
                else:
                    self._proxy_get(f"http://{PROXY_TARGET_IP}:{PORT}/rename/{sid}?title={urllib.parse.quote(title)}")
            else:
                self._json_response({'error': 'sid and title required'}, 400)

        elif path == '/refresh':
            if MACHINE_ROLE == 'primary':
                self._json_response(refresh_sessions())
            else:
                self._proxy_get(f"http://{PROXY_TARGET_IP}:{PORT}/refresh", timeout=60)

        elif path == '/' or path == '/index.html':
            self._serve_file('index.html')

        elif path.endswith('.html'):
            self._serve_file(path.lstrip('/'))

        elif path == '/sw.js':
            self._serve_file('sw.js', 'application/javascript')

        elif path == '/icon.png':
            self._serve_file('icon.png', 'image/png')

        elif path == '/search_index.json':
            self._serve_file('search_index.json', 'application/json')

        elif path == '/search':
            params = urllib.parse.parse_qs(parsed.query)
            query = params.get('q', [''])[0]
            if MACHINE_ROLE == 'primary':
                self._json_response(search_sessions(query))
            else:
                self._proxy_get(f"http://{PROXY_TARGET_IP}:{PORT}/search?q={urllib.parse.quote(query)}", timeout=30)

        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _serve_file(self, filename, content_type='text/html; charset=utf-8'):
        filepath = os.path.join(LOGS_DIR, filename)
        if os.path.isfile(filepath):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            with open(filepath, 'rb') as f:
                self.wfile.write(f.read())
        elif MACHINE_ROLE != 'primary':
            self._proxy_get(f"http://{PROXY_TARGET_IP}:{PORT}/{filename}", raw=True)
        else:
            self.send_response(404)
            self.end_headers()

    def _proxy_get(self, url, timeout=10, raw=False):
        """Proxy GET request to primary server."""
        try:
            resp = urllib.request.urlopen(url, timeout=timeout)
            data = resp.read()
            content_type = resp.headers.get('Content-Type', 'application/json')
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            if raw:
                self.send_response(502)
                self.end_headers()
            else:
                self._json_response({'status': 'error', 'message': str(e)}, 502)

    def _proxy_post(self, url, body):
        """Proxy POST request to primary server."""
        try:
            req = urllib.request.Request(
                url, data=body.encode(),
                headers={'Content-Type': 'application/json'}, method='POST'
            )
            resp = urllib.request.urlopen(req, timeout=10)
            self._json_response(json.loads(resp.read().decode()))
        except Exception as e:
            self._json_response({'status': 'error', 'message': str(e)}, 502)

    def log_message(self, format, *args):
        pass


# ─── Active Session Detection ───

_active_cache = []
_cache_lock = threading.Lock()


def _get_resume_sessions():
    """Extract --resume session IDs from running processes."""
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
        active = []
        for line in result.stdout.split('\n'):
            match = re.search(r'--resume\s+(\S+)', line)
            if match:
                active.append(match.group(1))
        return active
    except Exception:
        return []


def _refresh_cache():
    """Refresh active session cache every 5 seconds (primary only)."""
    global _active_cache
    while True:
        try:
            sessions = _get_resume_sessions()
            with _cache_lock:
                _active_cache = sessions
        except Exception:
            pass
        time.sleep(5)


def get_active_sessions():
    """Return active sessions."""
    if MACHINE_ROLE == 'primary':
        with _cache_lock:
            return {sid: {'machine': 'primary'} for sid in _active_cache}
    else:
        try:
            resp = urllib.request.urlopen(f"http://{PROXY_TARGET_IP}:{PORT}/active", timeout=5)
            return json.loads(resp.read().decode())
        except Exception:
            return {}


# ─── Session Start/Create (primary only) ───

def _open_terminal(sid):
    """Open Terminal.app and run claude --resume (macOS only)."""
    cmd = f"{CLAUDE_PATH} --resume {sid} --remote-control"
    subprocess.Popen([
        'osascript', '-e',
        f'tell application "Terminal"\n'
        f'do script "{cmd}"\n'
        f'activate\n'
        f'end tell'
    ])


def start_session(sid):
    """Start a session."""
    if MACHINE_ROLE == 'primary':
        try:
            with _cache_lock:
                if sid in _active_cache:
                    subprocess.Popen([
                        'osascript', '-e',
                        'tell application "Terminal" to activate'
                    ])
                    return {'status': 'ok', 'session': sid, 'action': 'already_running'}

            _open_terminal(sid)
            return {'status': 'ok', 'session': sid, 'action': 'started'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    else:
        try:
            url = f"http://{PROXY_TARGET_IP}:{PORT}/start/{sid}"
            resp = urllib.request.urlopen(url, timeout=30)
            result = json.loads(resp.read().decode())
            if result.get('status') == 'ok':
                subprocess.Popen(['open', 'https://claude.ai/code'])
            return result
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


def new_session(msg='hi'):
    """Create a new session."""
    if MACHINE_ROLE == 'primary':
        try:
            proj_dir = PROJECTS_DIR
            before = set()
            if os.path.isdir(proj_dir):
                before = set(f for f in os.listdir(proj_dir) if f.endswith('.jsonl'))

            env = os.environ.copy()
            env['PATH'] = os.path.expanduser('~/.local/bin') + ':' + env.get('PATH', '')
            subprocess.run(
                [CLAUDE_PATH, '-p', msg],
                capture_output=True, text=True, timeout=180,
                env=env, cwd=os.path.expanduser('~')
            )

            sid = None
            if os.path.isdir(proj_dir):
                after = set(f for f in os.listdir(proj_dir) if f.endswith('.jsonl'))
                new_files = after - before
                if new_files:
                    newest = max(new_files, key=lambda f: os.path.getmtime(os.path.join(proj_dir, f)))
                    sid = newest[:-6]

            if not sid:
                return {'status': 'error', 'message': 'session ID not found'}

            _open_terminal(sid)
            return {'status': 'ok', 'session': sid}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    else:
        try:
            url = f"http://{PROXY_TARGET_IP}:{PORT}/new-session?msg={urllib.parse.quote(msg)}"
            resp = urllib.request.urlopen(url, timeout=180)
            result = json.loads(resp.read().decode())
            if result.get('status') == 'ok':
                subprocess.Popen(['open', 'https://claude.ai/code'])
            return result
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


def stop_session(sid):
    """Stop a session by killing the claude process."""
    if MACHINE_ROLE == 'primary':
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
            killed = False
            for line in result.stdout.split('\n'):
                if f'--resume {sid}' in line:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        subprocess.run(['kill', pid], capture_output=True, timeout=5)
                        killed = True
            if killed:
                return {'status': 'ok', 'session': sid, 'action': 'stopped'}
            else:
                return {'status': 'ok', 'session': sid, 'action': 'not_found'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    else:
        try:
            url = f"http://{PROXY_TARGET_IP}:{PORT}/stop/{sid}"
            resp = urllib.request.urlopen(url, timeout=10)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


def search_sessions(query):
    """Full-text search in JSONL session files."""
    if not query or len(query) < 2:
        return []

    results = []
    proj_dir = PROJECTS_DIR
    if not os.path.isdir(proj_dir):
        return []

    query_lower = query.lower()
    summaries = {}
    summaries_path = os.path.join(LOGS_DIR, 'summaries.json')
    if os.path.isfile(summaries_path):
        with open(summaries_path, 'r', encoding='utf-8') as f:
            summaries = json.load(f)

    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))

    for fname in os.listdir(proj_dir):
        if not fname.endswith('.jsonl') or fname.startswith('agent-'):
            continue
        sid = fname[:-6]
        filepath = os.path.join(proj_dir, fname)

        try:
            count = 0
            snippet = ''
            msg_count = 0
            first_ts = None
            last_ts = None

            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts = obj.get('timestamp', '')
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(KST)
                            if first_ts is None:
                                first_ts = dt
                            last_ts = dt
                        except (ValueError, AttributeError):
                            pass

                    message = obj.get('message', {})
                    role = message.get('role', '')
                    if role in ('human', 'user', 'assistant'):
                        msg_count += 1

                    content = message.get('content', '')
                    if isinstance(content, list):
                        content = ' '.join(
                            b.get('text', '') for b in content
                            if isinstance(b, dict) and b.get('type') == 'text'
                        )
                    if not isinstance(content, str):
                        continue
                    content_lower = content.lower()
                    idx = content_lower.find(query_lower)
                    if idx != -1:
                        count += 1
                        if not snippet:
                            start = max(0, idx - 60)
                            end = min(len(content), idx + len(query) + 60)
                            snippet = content[start:end]
                            if start > 0:
                                snippet = '...' + snippet
                            if end < len(content):
                                snippet += '...'

            if count > 0:
                cached = summaries.get(sid, {})
                title = cached.get('title', sid[:8]) if isinstance(cached, dict) else cached

                start_date = first_ts.strftime('%Y-%m-%d %H:%M') if first_ts else ''
                end_date = last_ts.strftime('%Y-%m-%d %H:%M') if last_ts else ''

                duration = ''
                if first_ts and last_ts:
                    td = last_ts - first_ts
                    total_s = int(td.total_seconds())
                    if total_s < 60:
                        duration = f'{total_s}s'
                    elif total_s < 3600:
                        duration = f'{total_s // 60}m'
                    elif total_s < 86400:
                        h = total_s // 3600
                        m = (total_s % 3600) // 60
                        duration = f'{h}h {m}m' if m else f'{h}h'
                    else:
                        duration = f'{total_s // 86400}d'

                results.append({
                    'id': sid,
                    'title': title,
                    'start_date': start_date,
                    'end_date': end_date,
                    'duration': duration,
                    'msg_count': msg_count,
                    'count': count,
                    'snippet': snippet
                })
        except Exception:
            continue

    results.sort(key=lambda x: x['count'], reverse=True)
    return results


def rename_session(sid, title):
    """Rename a session title (primary only)."""
    try:
        convert_script = os.path.join(LOGS_DIR, 'convert_session.py')
        subprocess.run(
            ['python3', convert_script, '--rename', sid, title],
            capture_output=True, text=True, timeout=30
        )
        return {'status': 'ok', 'session': sid, 'title': title}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def refresh_sessions():
    """Run convert_session.py to regenerate HTML (primary only)."""
    try:
        convert_script = os.path.join(LOGS_DIR, 'convert_session.py')
        result = subprocess.run(
            ['python3', convert_script],
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout + result.stderr
        return {'status': 'ok', 'output': output.strip()[-200:]}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# ─── Main ───

if __name__ == '__main__':
    print(f"Machine role: {MACHINE_ROLE}")
    print(f"Projects dir: {PROJECTS_DIR}")

    if MACHINE_ROLE == 'primary':
        t = threading.Thread(target=_refresh_cache, daemon=True)
        t.start()
        time.sleep(1)

    class ThreadingServer(http.server.ThreadingHTTPServer):
        daemon_threads = True
    server = ThreadingServer(('0.0.0.0', PORT), SessionHandler)
    print(f'Session server on http://0.0.0.0:{PORT}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
