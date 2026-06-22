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
import ipaddress
import json
import logging
import logging.handlers
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

# ─── Request log (rotating, 10MB × 5 = 50MB max) ───
_LOG_PATH = os.path.join(LOGS_DIR, 'active_server.log')
_logger = logging.getLogger('active_server')
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    try:
        _h = logging.handlers.RotatingFileHandler(
            _LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
        )
        _h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        _logger.addHandler(_h)
    except Exception:
        pass  # Logging failure must not break the server.

# Polling endpoints excluded from the request log to keep it readable.
_NOISY_PATHS = ('/active', '/hidden', '/whoami')

# Default configuration
_config = {
    "port": 18080,
    "claude_path": os.path.expanduser("~/.local/bin/claude"),
    "remote_server_ip": "",       # Tailscale/VPN IP of the primary server (optional, for multi-machine setup)
    "proxy_target_ip": "",        # IP to proxy to (optional, for secondary machine)
    "machine_role": "auto",       # "auto", "primary", or "proxy"
    "allow_cidr": "100.64.0.0/10",  # private VPN range allowed to connect (+ loopback); default = Tailscale CGNAT
}

# Load config from file if exists
if os.path.isfile(CONFIG_PATH):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        _config.update(json.load(f))

PORT = _config["port"]
CLAUDE_PATH = _config["claude_path"]
PROXY_TARGET_IP = _config.get("proxy_target_ip", "")

# Access control: requests are allowed only from loopback or this private VPN range.
# Default = Tailscale CGNAT (100.64.0.0/10); override via config "allow_cidr" for a
# different VPN. allow_cidr must sit inside private/VPN/loopback space — a malformed,
# wide-open (0.0.0.0/0, ::/0), or public value falls back to the secure default, so
# config can never open the allowlist to the public internet.
_PRIVATE_SUPERNETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT (Tailscale)
    ipaddress.ip_network("127.0.0.0/8"),     # loopback
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique-local
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
]

def _parse_allowed_net(value):
    default = ipaddress.ip_network("100.64.0.0/10")
    try:
        net = ipaddress.ip_network(value, strict=False)
    except (ValueError, TypeError):
        return default
    for sn in _PRIVATE_SUPERNETS:
        if net.version == sn.version and net.subnet_of(sn):
            return net
    _logger.warning("allow_cidr %r is not a private/VPN range; using secure default %s", value, default)
    return default

_ALLOWED_NET = _parse_allowed_net(_config.get("allow_cidr", "100.64.0.0/10"))

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
    def _log_request(self, method):
        """One-line request log; skip polling endpoints."""
        try:
            path = urllib.parse.urlparse(self.path).path
            for p in _NOISY_PATHS:
                if path == p or path.startswith(p):
                    return
            client = self.client_address[0] if self.client_address else '-'
            ua = (self.headers.get('User-Agent', '-') or '-')[:160]
            _logger.info(f'{method} {self.path} client={client} ua="{ua}"')
        except Exception:
            pass

    # ─── Access control ───
    # The server binds 0.0.0.0 (all interfaces) so it works regardless of when the VPN
    # comes up, but every request's source IP is checked: only loopback and the configured
    # private VPN range (default Tailscale CGNAT 100.64.0.0/10) are allowed; everything
    # else (public/LAN direct access) gets 403. This IP allowlist is the only thing that
    # keeps the dashboard private — never expose the port publicly (no router port-forward,
    # no Tailscale Funnel/Serve, no cloud inbound rule).
    def _client_allowed(self):
        """True if the requester IP is loopback or within the allowed VPN range."""
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except (ValueError, IndexError, TypeError):
            return False
        return ip.is_loopback or ip in _ALLOWED_NET

    def _deny_forbidden(self):
        self.send_response(403)
        self.send_header('Content-Length', '0')  # be explicit for HTTP/1.1 keep-alive
        self.end_headers()

    # State-changing (side-effect) paths are CSRF-guarded; read-only paths are exempt.
    # /refresh re-runs conversion and regenerates files, so it counts as state-changing.
    _STATE_CHANGE_PATHS = ('/start/', '/stop/', '/new-session', '/rename/', '/hidden-update', '/refresh')

    def _is_state_change(self, path):
        for p in self._STATE_CHANGE_PATHS:
            if path == p or path.startswith(p):
                return True
        return False

    def _csrf_ok(self):
        """Block cross-site requests to state-changing endpoints. The IP allowlist alone
        cannot stop a malicious page loaded on an *allowed* device from triggering session
        start/stop via <img> or fetch(no-cors). Prefer Sec-Fetch-Site (allow only
        same-origin/none); fall back to Origin (reject 'null' or a host mismatch). If
        neither header is present, fail open and log it (non-browser/legacy clients).
        Modern browsers always send Sec-Fetch-Site and cannot disable it from JS, so
        browser-driven cross-site attacks are rejected; the only residual gap is a client
        that sends neither Sec-Fetch-Site nor Origin (non-browser, or a legacy webview)."""
        sfs = (self.headers.get('Sec-Fetch-Site') or '').strip().lower()
        if sfs:
            return sfs in ('same-origin', 'none')
        origin = (self.headers.get('Origin') or '').strip()
        if origin:
            if origin.lower() == 'null':
                return False
            try:
                o_netloc = urllib.parse.urlparse(origin).netloc.lower()
            except Exception:
                return False
            host = (self.headers.get('Host') or '').strip().lower()
            return bool(o_netloc) and o_netloc == host
        # Neither header present → fail open + observability log (to spot header-less clients).
        try:
            client = self.client_address[0] if self.client_address else '-'
            ua = (self.headers.get('User-Agent', '-') or '-')[:160]
            _logger.info(f'CSRF-failopen(no headers) {self.command} '
                         f'{urllib.parse.urlparse(self.path).path} client={client} ua="{ua}"')
        except Exception:
            pass
        return True

    def _deny_csrf(self):
        try:
            client = self.client_address[0] if self.client_address else '-'
            _logger.info(f'CSRF-deny {self.command} {urllib.parse.urlparse(self.path).path} '
                         f'sfs="{self.headers.get("Sec-Fetch-Site","")}" '
                         f'origin="{self.headers.get("Origin","")}" client={client}')
        except Exception:
            pass
        self.send_response(403)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def end_headers(self):
        # Defense-in-depth on every response: the dashboard UI is never meant to be
        # embedded, so block framing (clickjacking). A malicious page that frames the
        # dashboard would run same-origin and could otherwise trigger state-changing
        # clicks. Harmless on JSON/error responses.
        self.send_header('X-Frame-Options', 'DENY')
        super().end_headers()

    def do_HEAD(self):
        # Gate unimplemented verbs through the same allowlist so a disallowed IP always
        # gets 403 (not the 501 a bare BaseHTTPRequestHandler would return).
        if not self._client_allowed():
            self._deny_forbidden()
            return
        # The same-origin PWA only uses GET/POST; HEAD is not served.
        self.send_response(405)
        self.send_header('Allow', 'GET, POST')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_OPTIONS(self):
        if not self._client_allowed():
            self._deny_forbidden()
            return
        # No CORS, so no preflight is expected; report method not allowed.
        self.send_response(405)
        self.send_header('Allow', 'GET, POST')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        if not self._client_allowed():
            self._deny_forbidden()
            return
        self._log_request('POST')
        path = urllib.parse.urlparse(self.path).path
        if self._is_state_change(path) and not self._csrf_ok():
            self._deny_csrf()
            return
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
        if not self._client_allowed():
            self._deny_forbidden()
            return
        self._log_request('GET')
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if self._is_state_change(path) and not self._csrf_ok():
            self._deny_csrf()
            return

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
        # No CORS header: this is a same-origin PWA; allowing any origin would let a
        # malicious page on an allowlisted device read session/search data cross-origin.
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _serve_file(self, filename, content_type='text/html; charset=utf-8'):
        filepath = os.path.join(LOGS_DIR, filename)
        real = os.path.realpath(filepath)
        base = os.path.realpath(LOGS_DIR)
        # 경로 트래버설 차단: LOGS_DIR 경계 밖이면 거부 (proxy도 하지 않음)
        if real != base and not real.startswith(base + os.sep):
            self.send_response(404)
            self.end_headers()
            return
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
            # No CORS header (same-origin PWA; see _json_response).
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

# Dedupe: block duplicate /new-session calls with the same message within a short
# window. Prevents double-tap, network retry, or iOS auto-retry from spawning
# two sessions for one user intent. Only successful results are cached so
# error-then-retry still works.
_new_session_dedupe = {}  # msg -> (timestamp, result)
_DEDUPE_WINDOW_SEC = 30
_dedupe_lock = threading.Lock()


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
        # ── Dedupe check ──
        now = time.time()
        with _dedupe_lock:
            expired = [k for k, (ts, _) in _new_session_dedupe.items() if now - ts > _DEDUPE_WINDOW_SEC]
            for k in expired:
                _new_session_dedupe.pop(k, None)
            cached = _new_session_dedupe.get(msg)
            if cached:
                age = now - cached[0]
                _logger.info(f'new-session dedupe HIT (age={age:.1f}s) sid={cached[1].get("session","?")}')
                return cached[1]

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
            result = {'status': 'ok', 'session': sid}
            with _dedupe_lock:
                _new_session_dedupe[msg] = (time.time(), result)
            return result
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
