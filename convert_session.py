#!/usr/bin/env python3
"""
Convert Claude Code JSONL session logs to browseable HTML pages.

Usage:
  python3 convert_session.py                    # Convert all sessions (incremental)
  python3 convert_session.py <session_id>       # Convert specific session
  python3 convert_session.py --force            # Force reconvert all sessions
  python3 convert_session.py --rename <sid> "New Title"  # Rename session title
"""

import json
import sys
import os
import glob
import re
import html
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Configuration ───

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.environ.get("CLAUDE_DASHBOARD_DIR", SCRIPT_DIR)
SUMMARIES_PATH = os.path.join(OUTPUT_DIR, "summaries.json")

# Auto-detect PROJECTS_DIR
def _find_projects_dir():
    base = os.path.expanduser("~/.claude/projects")
    if os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            full = os.path.join(base, entry)
            if os.path.isdir(full) and entry.startswith("-"):
                return full
    return base

PROJECTS_DIR = os.environ.get("CLAUDE_PROJECTS_DIR", _find_projects_dir())

# Timezone: override with CLAUDE_DASHBOARD_TZ env var (e.g., "9" for KST, "-5" for EST)
_tz_offset = int(os.environ.get("CLAUDE_DASHBOARD_TZ", "9"))
LOCAL_TZ = timezone(timedelta(hours=_tz_offset))


def to_local(dt):
    """Convert datetime to local timezone."""
    return dt.astimezone(LOCAL_TZ)


def format_duration(td):
    """Convert timedelta to human-readable string."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "0s"
    if total_seconds < 60:
        return f"{total_seconds}s"
    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"{total_minutes}m"
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours < 24:
        if minutes == 0:
            return f"{hours}h"
        return f"{hours}h {minutes}m"
    days = hours // 24
    if days < 7:
        return f"{days}d"
    weeks = days // 7
    if days < 30:
        return f"{weeks}w"
    months = days // 30
    if months < 12:
        return f"{months}mo"
    years = days // 365
    remaining_months = (days - years * 365) // 30
    if remaining_months == 0:
        return f"{years}y"
    return f"{years}y {remaining_months}mo"


def load_summaries():
    """Load cached summaries."""
    if os.path.exists(SUMMARIES_PATH):
        with open(SUMMARIES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_summaries(summaries):
    """Save summaries cache."""
    with open(SUMMARIES_PATH, 'w', encoding='utf-8') as f:
        json.dump(summaries, ensure_ascii=False, indent=2, fp=f)


def extract_conversation_text(jsonl_path, max_chars=4000):
    """Extract conversation text from JSONL (for summarization)."""
    user_texts = []
    assistant_texts = []
    user_total = 0
    assistant_total = 0
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = obj.get('message', {})
            role = message.get('role', '')
            content = message.get('content', '')
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = ' '.join(
                    b.get('text', '') for b in content
                    if isinstance(b, dict) and b.get('type') == 'text'
                )
            else:
                continue
            text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL).strip()
            if not text:
                continue
            if role in ('human', 'user'):
                if user_total < 2500:
                    user_texts.append(f"User: {text}\n")
                    user_total += len(text)
            elif role == 'assistant':
                if assistant_total < 1500:
                    assistant_texts.append(f"Claude: {text}\n")
                    assistant_total += len(text)
    combined = ''.join(user_texts) + '\n---\n' + ''.join(assistant_texts)
    return combined[:max_chars]


def summarize_session_api(conversation_text):
    """Call Anthropic API to generate a session title summary."""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return None

    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 100,
        "messages": [{
            "role": "user",
            "content": (
                "Below is a conversation between a user and Claude.\n"
                "Summarize what the user was trying to accomplish in one line (under 40 characters).\n"
                "Focus on the user's intent, not Claude's response. Output only the summary.\n\n"
                'Good: "Build PubMed paper weekly digest pipeline"\n'
                'Good: "Set up Naver cafe keyword monitoring"\n'
                'Bad: "Yes, I understand. Let me proceed."\n\n'
                f"---\n{conversation_text}"
            )
        }]
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01'
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            for block in result.get('content', []):
                if block.get('type') == 'text':
                    return block['text'].strip()
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        print(f"    Warning: Summary API error: {e}")
    return None


def count_messages(jsonl_path):
    """Count user + assistant messages in JSONL file."""
    count = 0
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    role = obj.get('message', {}).get('role', '')
                    if role in ('human', 'user', 'assistant'):
                        count += 1
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return count


def get_summary(session_id, jsonl_path, summaries_cache):
    """Get summary from cache, or call API if missing/stale."""
    RESUMMARIZE_THRESHOLD = 20

    cached = summaries_cache.get(session_id)
    current_msg_count = count_messages(jsonl_path)

    if cached:
        if isinstance(cached, str):
            cached = {'title': cached, 'msg_count': 0}
            summaries_cache[session_id] = cached

        old_count = cached.get('msg_count', 0)
        if current_msg_count - old_count >= RESUMMARIZE_THRESHOLD:
            conversation_text = extract_conversation_text(jsonl_path)
            if conversation_text:
                new_title = summarize_session_api(conversation_text)
                if new_title:
                    cached['title'] = new_title
                    cached['msg_count'] = current_msg_count
                    print(f"    Re-summarized: {new_title[:40]}")
        return cached.get('title')

    conversation_text = extract_conversation_text(jsonl_path)
    if not conversation_text:
        return None

    summary = summarize_session_api(conversation_text)
    if summary:
        summaries_cache[session_id] = {
            'title': summary,
            'msg_count': current_msg_count
        }
    return summary


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
<style>
  :root {{
    --bg: #faf9f5;
    --surface: #fff;
    --surface2: #f0efe8;
    --user-bg: #788c5d;
    --assistant-bg: #d97757;
    --text: #141413;
    --text-muted: #b0aea5;
    --border: #e8e6dc;
    --code-bg: #f4f3ee;
    --accent: #d97757;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #141413;
      --surface: #1e1e1c;
      --surface2: #2a2a27;
      --user-bg: #788c5d;
      --assistant-bg: #d97757;
      --text: #faf9f5;
      --text-muted: #b0aea5;
      --border: #2a2a27;
      --code-bg: #1a1a18;
      --accent: #d97757;
    }}
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }}
  .header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 20px 40px;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(10px);
  }}
  .header h1 {{ font-size: 1.2em; font-weight: 600; }}
  .header .meta {{ color: var(--text-muted); font-size: 0.85em; margin-top: 4px; }}
  .header .nav {{ margin-top: 8px; }}
  .header .nav a {{
    color: var(--accent);
    text-decoration: none;
    font-size: 0.85em;
    margin-right: 16px;
  }}
  .header .nav a:hover {{ text-decoration: underline; }}
  .session-id {{
    cursor: pointer;
    border-bottom: 1px dashed var(--text-muted);
  }}
  .session-id:hover {{ color: var(--accent); }}
  .title-wrap {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }}
  .title-edit-btn {{
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px 8px;
    font-size: 0.75em;
    white-space: nowrap;
  }}
  .title-edit-btn:hover {{ color: var(--accent); border-color: var(--accent); }}
  .title-input {{
    font-size: 1.2em;
    font-weight: 600;
    background: var(--code-bg);
    color: var(--text);
    border: 2px solid var(--accent);
    border-radius: 6px;
    padding: 4px 8px;
    width: 100%;
    outline: none;
  }}
  .container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
  }}
  .message {{
    margin: 16px 0;
    padding: 16px 20px;
    border-radius: 12px;
    position: relative;
  }}
  .message.user {{
    background: var(--surface);
    border-left: 4px solid var(--user-bg);
  }}
  .message.assistant {{
    background: var(--surface);
    border-left: 4px solid var(--assistant-bg);
  }}
  .message.system {{
    background: var(--surface2);
    border-left: 4px solid var(--text-muted);
    font-size: 0.85em;
    color: var(--text-muted);
  }}
  .role {{
    font-size: 0.75em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }}
  .message.user .role {{ color: var(--user-bg); }}
  .message.assistant .role {{ color: var(--assistant-bg); }}
  .message.system .role {{ color: var(--text-muted); }}
  .content {{ word-wrap: break-word; line-height: 1.6; }}
  .content pre {{ white-space: pre-wrap; word-wrap: break-word; }}
  .content ul, .content ol {{ padding-left: 1.5em; margin: 8px 0; }}
  .content li {{ margin: 4px 0; }}
  .content blockquote {{ border-left: 3px solid var(--text-muted); padding-left: 12px; margin: 8px 0; color: var(--text-muted); }}
  .content table {{ border-collapse: collapse; margin: 8px 0; width: 100%; }}
  .content th, .content td {{ border: 1px solid var(--border); padding: 6px 10px; text-align: left; }}
  .content th {{ background: var(--code-bg); }}
  .content h1, .content h2, .content h3 {{ margin: 12px 0 8px; }}
  .content hr {{ border: none; border-top: 1px solid var(--border); margin: 12px 0; }}
  .content p {{ margin: 8px 0; }}
  .tool-use {{
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin: 8px 0;
    font-size: 0.85em;
  }}
  .tool-use summary {{
    cursor: pointer;
    font-weight: 600;
    color: var(--accent);
  }}
  .tool-use pre {{
    margin-top: 8px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  code {{
    background: var(--code-bg);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: 'SF Mono', 'Fira Code', monospace;
  }}
  pre {{
    background: var(--code-bg);
    padding: 12px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 8px 0;
  }}
  pre code {{
    background: none;
    padding: 0;
  }}
  .timestamp {{
    color: var(--text-muted);
    font-size: 0.75em;
    float: right;
  }}
  .search-highlight {{
    background: yellow;
    color: black;
    padding: 1px 2px;
    border-radius: 2px;
  }}
  @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
</style>
</head>
<body data-sid="{session_id}" data-jsonl-size="{jsonl_size}">
<div class="header">
  <div class="title-wrap">
    <h1 id="sessionTitle">{title}</h1>
    <button class="title-edit-btn" onclick="startTitleEdit()">Edit</button>
  </div>
  <div class="meta">{meta}</div>
  <div style="margin-top:6px;font-size:0.85em;">
    <span id="activeInfo"></span>
  </div>
  <div class="nav">
    <a href="index.html">Back to list</a>
    <a href="search.html">Search</a>
    <a href="#" onclick="exportPage(); return false;">Export</a>
    <button id="resumeBtn" onclick="resumeSession()" style="padding:4px 12px;border:1px solid var(--accent);border-radius:6px;background:var(--accent);color:#fff;font-size:0.85em;cursor:pointer;">Resume</button>
    <button id="hideBtn" onclick="toggleHideSession()" style="padding:4px 12px;border:1px solid var(--border);border-radius:6px;background:none;color:var(--text-muted);font-size:0.85em;cursor:pointer;margin-left:4px;">Hide</button>
  </div>
</div>
<div class="container">
{messages}
</div>
<script>
function copyText(text, el) {{
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).catch(function() {{}});
  }} else {{
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }}
  var orig = el.textContent;
  el.textContent = 'Copied!';
  setTimeout(function() {{ el.textContent = orig; }}, 5000);
}}
</script>
<script>
(function() {{
  function timeAgo(date) {{
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    if (seconds < 0) return 'just now';
    if (seconds < 60) return seconds + 's ago';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + 'm ago';
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + 'h ago';
    const days = Math.floor(hours / 24);
    if (days < 30) return days + 'd ago';
    const months = Math.floor(days / 30);
    if (months < 12) return months + 'mo ago';
    const years = Math.floor(days / 365);
    return years + 'y ago';
  }}
  document.querySelectorAll('.time-ago').forEach(function(el) {{
    var d = new Date(el.dataset.time);
    el.textContent = timeAgo(d);
  }});
}})();
</script>
<script>
(function() {{
  if (typeof marked === 'undefined') return;
  marked.setOptions({{
    highlight: function(code, lang) {{
      if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {{
        return hljs.highlight(code, {{language: lang}}).value;
      }}
      return code;
    }},
    breaks: true,
    gfm: true
  }});
  function b64DecodeUTF8(str) {{
    var bytes = Uint8Array.from(atob(str), function(c) {{ return c.charCodeAt(0); }});
    return new TextDecoder('utf-8').decode(bytes);
  }}
  document.querySelectorAll('.markdown-raw').forEach(function(el) {{
    var raw = b64DecodeUTF8(el.dataset.md);
    el.innerHTML = marked.parse(raw);
  }});
}})();
</script>
<script>
var SID = document.body.dataset.sid;
var TITLE_KEY = 'title_' + SID;
var ORIGINAL_TITLE = document.getElementById('sessionTitle').textContent;

(function loadCustomTitle() {{
  var saved = localStorage.getItem(TITLE_KEY);
  if (saved) {{
    document.getElementById('sessionTitle').textContent = saved;
    document.title = saved;
    addEditedBadge();
  }}
}})();

(function() {{
  var sid = document.body.dataset.sid;
  fetch('/active')
    .then(function(r) {{ return r.json(); }})
    .then(function(activeMap) {{
      var info = activeMap[sid];
      if (info) {{
        var el = document.getElementById('activeInfo');
        el.innerHTML = '<span style="display:inline-block;width:8px;height:8px;background:#d97757;border-radius:50%;animation:pulse 1.5s ease-in-out infinite;vertical-align:middle;margin-right:4px;"></span><span style="color:#d97757;font-weight:600;">Active</span>';
      }}
    }})
    .catch(function() {{}});
}})();

function addEditedBadge() {{
  if (document.getElementById('editedBadge')) return;
  var badge = document.createElement('span');
  badge.id = 'editedBadge';
  badge.textContent = '(edited)';
  badge.style.cssText = 'font-size:0.6em; color:var(--text-muted); font-weight:400; margin-left:8px;';
  document.getElementById('sessionTitle').appendChild(badge);
}}

function startTitleEdit() {{
  var h1 = document.getElementById('sessionTitle');
  var current = localStorage.getItem(TITLE_KEY) || ORIGINAL_TITLE;
  var wrap = h1.parentElement;
  var input = document.createElement('input');
  input.type = 'text';
  input.value = current;
  input.className = 'title-input';
  h1.style.display = 'none';
  wrap.querySelector('.title-edit-btn').style.display = 'none';
  wrap.insertBefore(input, h1);
  input.focus();
  input.select();

  function finish(val) {{
    input.remove();
    h1.style.display = '';
    wrap.querySelector('.title-edit-btn').style.display = '';
    if (val !== null && val !== current) {{
      var oldBadge = document.getElementById('editedBadge');
      if (oldBadge) oldBadge.remove();
      h1.textContent = val;
      document.title = val;
      localStorage.setItem(TITLE_KEY, val);
      fetch('/rename/' + SID + '?title=' + encodeURIComponent(val)).catch(function() {{}});
      addEditedBadge();
    }}
  }}
  input.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter') {{ var v = input.value.trim(); finish(v || current); }}
    if (e.key === 'Escape') finish(null);
  }});
  input.addEventListener('blur', function() {{
    var v = input.value.trim();
    finish(v || current);
  }});
}}

function exportPage() {{
  var clone = document.documentElement.cloneNode(true);
  clone.querySelectorAll('.markdown-raw').forEach(function(el) {{
    el.removeAttribute('data-md');
    el.classList.remove('markdown-raw');
  }});
  clone.querySelectorAll('script[src], link[href*="cdn"]').forEach(function(el) {{ el.remove(); }});
  var html = '<!DOCTYPE html>\\n<html lang="en">' + clone.innerHTML + '</html>';
  var blob = new Blob([html], {{type: 'text/html;charset=utf-8'}});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = document.title.replace(/[^\\w\\s-]/g, '').trim() + '.html';
  a.click();
  URL.revokeObjectURL(a.href);
}}

(function() {{
  var sid = document.body.dataset.sid;
  var btn = document.getElementById('hideBtn');
  fetch('/hidden')
    .then(function(r) {{ return r.json(); }})
    .then(function(list) {{
      var hidden = new Set(list);
      if (hidden.has(sid)) {{
        btn.textContent = 'Unhide';
        btn.style.borderColor = 'var(--accent)';
        btn.style.color = 'var(--accent)';
      }}
    }})
    .catch(function() {{}});
}})();

window.toggleHideSession = function() {{
  var sid = document.body.dataset.sid;
  var btn = document.getElementById('hideBtn');
  btn.disabled = true;
  fetch('/hidden')
    .then(function(r) {{ return r.json(); }})
    .then(function(list) {{
      var hidden = new Set(list);
      if (hidden.has(sid)) {{
        hidden.delete(sid);
        btn.textContent = 'Hide';
        btn.style.borderColor = 'var(--border)';
        btn.style.color = 'var(--text-muted)';
      }} else {{
        hidden.add(sid);
        btn.textContent = 'Unhide';
        btn.style.borderColor = 'var(--accent)';
        btn.style.color = 'var(--accent)';
      }}
      return fetch('/hidden-update', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(Array.from(hidden))
      }});
    }})
    .then(function() {{ btn.disabled = false; }})
    .catch(function() {{ btn.disabled = false; }});
}};

function resumeSession() {{
  var sid = document.body.dataset.sid;
  var btn = document.getElementById('resumeBtn');
  btn.textContent = 'Starting...';
  btn.disabled = true;
  fetch('/start/' + sid)
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.status === 'ok') {{
        btn.textContent = 'Active';
        btn.style.background = '#788c5d';
        btn.style.borderColor = '#788c5d';
      }} else {{
        btn.textContent = 'Failed';
        alert('Failed to start session: ' + (data.message || ''));
      }}
    }})
    .catch(function() {{
      btn.textContent = 'Resume';
      btn.disabled = false;
      alert('Cannot connect to server.');
    }});
}}
</script>
<div style="position:fixed;right:16px;bottom:16px;display:flex;flex-direction:column;gap:8px;z-index:200;">
  <button onclick="window.scrollTo({{top:0,behavior:'smooth'}})" style="width:40px;height:40px;border-radius:50%;border:1px solid var(--border);background:var(--surface);color:var(--text-muted);font-size:1.2em;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.15);">&#9650;</button>
  <button onclick="window.scrollTo({{top:document.body.scrollHeight,behavior:'smooth'}})" style="width:40px;height:40px;border-radius:50%;border:1px solid var(--border);background:var(--surface);color:var(--text-muted);font-size:1.2em;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.15);">&#9660;</button>
</div>
</body>
</html>"""


def markdown_to_html(text):
    """Simple markdown to HTML conversion."""
    if not text:
        return ""
    text = html.escape(text)
    text = re.sub(
        r'```(\w*)\n(.*?)```',
        lambda m: f'<pre><code class="lang-{m.group(1)}">{m.group(2)}</code></pre>',
        text, flags=re.DOTALL
    )
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    text = text.replace('\n', '<br>\n')
    return text


def extract_text_from_content(content, role='assistant'):
    """Extract text from message content, handling tool_use blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    parts.append(block.get('text', ''))
                elif block.get('type') == 'tool_use':
                    tool_name = block.get('name', 'unknown')
                    tool_input = block.get('input', {})
                    input_str = json.dumps(tool_input, ensure_ascii=False, indent=2)
                    if len(input_str) > 500:
                        input_str = input_str[:500] + '\n... (truncated)'
                    parts.append(
                        f'<details class="tool-use"><summary>Tool: {html.escape(tool_name)}</summary>'
                        f'<pre>{html.escape(input_str)}</pre></details>'
                    )
                elif block.get('type') == 'tool_result':
                    if role in ('human', 'user'):
                        continue
                    result_content = block.get('content', '')
                    if isinstance(result_content, list):
                        for rc in result_content:
                            if isinstance(rc, dict) and rc.get('type') == 'text':
                                result_text = rc.get('text', '')
                                if len(result_text) > 300:
                                    result_text = result_text[:300] + '... (truncated)'
                                parts.append(
                                    f'<details class="tool-use"><summary>Tool Result</summary>'
                                    f'<pre>{html.escape(result_text)}</pre></details>'
                                )
                    elif isinstance(result_content, str):
                        if len(result_content) > 300:
                            result_content = result_content[:300] + '... (truncated)'
                        parts.append(
                            f'<details class="tool-use"><summary>Tool Result</summary>'
                            f'<pre>{html.escape(result_content)}</pre></details>'
                        )
        return '\n'.join(parts)
    return str(content)


def build_session_meta_html(session_id, start_dt, end_dt, msg_count):
    """Build meta HTML for session detail page header."""
    start_str = start_dt.strftime('%Y-%m-%d %H:%M')
    if start_dt.date() == end_dt.date():
        end_str = end_dt.strftime('%H:%M')
    else:
        end_str = end_dt.strftime('%Y-%m-%d %H:%M')
    duration = format_duration(end_dt - start_dt)
    end_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%S+09:00')

    short_id = session_id[:8]
    is_agent = session_id.startswith('agent-')

    if is_agent:
        return (
            f'<span class="session-id" '
            f'title="Sub-agent session (cannot resume)" '
            f'style="cursor:default;opacity:0.6">'
            f'Session: {short_id}...</span>'
            f' | {start_str} &rarr; {end_str} ({duration}) | {msg_count} messages'
            f' | <span class="time-ago" data-time="{end_iso}"></span>'
        )

    copy_cmd = f'claude --resume {session_id} --remote-control'
    return (
        f'<span class="session-id" '
        f"onclick=\"copyText('{copy_cmd}',this)\" "
        f'title="Click to copy: {copy_cmd}">'
        f'Session: {short_id}...</span>'
        f' | {start_str} &rarr; {end_str} ({duration}) | {msg_count} messages'
        f' | <span class="time-ago" data-time="{end_iso}"></span>'
    )


def convert_session(jsonl_path, summaries_cache=None):
    """Convert a JSONL session file to HTML."""
    session_id = Path(jsonl_path).stem
    messages_html = []
    first_user_msg = ""
    msg_count = 0
    first_dt = None
    last_dt = None

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get('type', '')
            timestamp = obj.get('timestamp', '')
            dt = None
            time_str = ''
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    dt_local = to_local(dt)
                    time_str = dt_local.strftime('%H:%M:%S')
                    if first_dt is None:
                        first_dt = dt_local
                    last_dt = dt_local
                except (ValueError, AttributeError):
                    pass

            message = obj.get('message', {})
            role = message.get('role', msg_type)
            content = message.get('content', '')

            if not content:
                continue

            text = extract_text_from_content(content, role=role)
            if not text or not text.strip():
                continue

            # Remove system-reminder and local command tags
            text_clean = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL).strip()
            text_clean = re.sub(r'<local-command-caveat>.*?</local-command-caveat>', '', text_clean, flags=re.DOTALL).strip()
            text_clean = re.sub(r'<command-name>.*?</command-name>', '', text_clean, flags=re.DOTALL).strip()
            text_clean = re.sub(r'<command-message>.*?</command-message>', '', text_clean, flags=re.DOTALL).strip()
            text_clean = re.sub(r'<command-args>.*?</command-args>', '', text_clean, flags=re.DOTALL).strip()
            text_clean = re.sub(r'<local-command-stdout>.*?</local-command-stdout>', '', text_clean, flags=re.DOTALL).strip()
            if not text_clean:
                continue

            # Filter system-injected skill prompts
            if role in ('human', 'user') and re.match(r'^#\s+\w+.*Skill', text_clean):
                continue

            if role in ('human', 'user'):
                role_class = 'user'
                role_label = 'User'
                if not first_user_msg:
                    plain = re.sub(r'<[^>]+>', '', text_clean)
                    first_user_msg = plain[:80].strip()
            elif role in ('assistant',):
                role_class = 'assistant'
                role_label = 'Claude'
            else:
                role_class = 'system'
                role_label = role.capitalize()

            if '<details' in text_clean or '<pre>' in text_clean:
                rendered = text_clean
            else:
                encoded = base64.b64encode(text_clean.encode('utf-8')).decode('ascii')
                rendered = f'<div class="markdown-raw" data-md="{encoded}"></div>'

            time_html = f'<span class="timestamp">{time_str}</span>' if time_str else ''
            messages_html.append(
                f'<div class="message {role_class}">'
                f'{time_html}'
                f'<div class="role">{role_label}</div>'
                f'<div class="content">{rendered}</div>'
                f'</div>'
            )
            msg_count += 1

    if msg_count == 0:
        return None

    if first_dt is None:
        first_dt = datetime.now(LOCAL_TZ)
    if last_dt is None:
        last_dt = first_dt

    summary = None
    if summaries_cache is not None:
        summary = get_summary(session_id, jsonl_path, summaries_cache)
    title = summary if summary else (first_user_msg if first_user_msg else session_id[:8])
    title = title.replace('\n', ' ').replace('\r', ' ').strip()

    meta = build_session_meta_html(session_id, first_dt, last_dt, msg_count)

    jsonl_size = os.path.getsize(jsonl_path)
    output_html = HTML_TEMPLATE.format(
        title=html.escape(title),
        session_id=session_id,
        jsonl_size=jsonl_size,
        meta=meta,
        messages='\n'.join(messages_html)
    )

    output_path = os.path.join(OUTPUT_DIR, f"{session_id}.html")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_html)

    return {
        'session_id': session_id,
        'title': title,
        'start_date': first_dt.strftime('%Y-%m-%d %H:%M'),
        'end_date': last_dt.strftime('%Y-%m-%d %H:%M'),
        'duration': format_duration(last_dt - first_dt),
        'msg_count': msg_count,
        'path': output_path
    }


def build_index(sessions):
    """Generate the index page (excludes agent sessions)."""
    sessions = [s for s in sessions if not s['session_id'].startswith('agent-')]
    sessions.sort(key=lambda s: s.get('end_date', s.get('date', '')), reverse=True)

    rows = []
    for s in sessions:
        start = s.get('start_date', s.get('date', ''))
        end = s.get('end_date', start)
        duration = s.get('duration', '')
        end_iso = ''
        if end:
            end_iso = end.replace(' ', 'T') + ':00+09:00'

        rows.append(
            f'<tr data-sid="{s["session_id"]}">'
            f'<td><a href="{s["session_id"]}.html" data-sid="{s["session_id"]}">{html.escape(s["title"])}</a></td>'
            f'<td class="sid-cell" data-sid="{s["session_id"]}">{s["session_id"][:8]}</td>'
            f'<td class="start-cell"></td>'
            f'<td class="time-ago" data-time="{end_iso}"></td>'
            f'<td>{html.escape(start)}</td>'
            f'<td>{html.escape(end)}</td>'
            f'<td>{html.escape(duration)}</td>'
            f'<td>{s["msg_count"]}</td>'
            f'</tr>'
        )

    tbody_content = ''.join(rows)

    INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Claude Logs">
<title>Claude Code Session Dashboard</title>
<style>
  :root {
    --bg: #faf9f5;
    --surface: #fff;
    --text: #141413;
    --text-muted: #b0aea5;
    --border: #e8e6dc;
    --accent: #d97757;
    --accent-hover: #c4623f;
    --blue: #6a9bcc;
    --green: #788c5d;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #141413;
      --surface: #1e1e1c;
      --text: #faf9f5;
      --text-muted: #b0aea5;
      --border: #2a2a27;
      --accent: #d97757;
      --accent-hover: #e8896b;
      --blue: #6a9bcc;
      --green: #788c5d;
    }
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 40px;
  }
  .claude-bot-wrap {
    display: flex;
    align-items: flex-end;
    gap: 20px;
    margin-bottom: 24px;
  }
  .claude-bot-wrap h1 {
    font-size: 1.4em;
    font-weight: 600;
    color: var(--text);
  }
  .claude-bot-svg {
    flex-shrink: 0;
    animation: pixel-hop 1s steps(2) infinite;
  }
  .claude-bot-svg .eye {
    animation: pixel-blink 3s steps(1) infinite;
  }
  .claude-bot-svg .leg1 { animation: pixel-walk-a 0.5s steps(1) infinite; }
  .claude-bot-svg .leg2 { animation: pixel-walk-b 0.5s steps(1) infinite; }
  .claude-bot-svg .leg3 { animation: pixel-walk-a 0.5s steps(1) infinite 0.25s; }
  .claude-bot-svg .leg4 { animation: pixel-walk-b 0.5s steps(1) infinite 0.25s; }
  @keyframes pixel-hop {
    0%,100% { transform: translateY(0); }
    50% { transform: translateY(-4px); }
  }
  @keyframes pixel-blink {
    0%,40%,50%,100% { opacity: 1; }
    44%,48% { opacity: 0; }
  }
  @keyframes pixel-walk-a {
    0%,100% { transform: translateY(0); }
    50% { transform: translateY(3px); }
  }
  @keyframes pixel-walk-b {
    0%,100% { transform: translateY(3px); }
    50% { transform: translateY(0); }
  }
  .subtitle { color: var(--text-muted); margin-bottom: 24px; font-size: 0.9em; }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  thead {
    position: sticky;
    top: 0;
    z-index: 10;
  }
  th, td {
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
  }
  th {
    background: var(--accent);
    color: #fff;
    font-size: 0.75em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
    border-bottom: 2px solid var(--accent-hover);
  }
  td a {
    color: var(--accent);
    text-decoration: none;
  }
  td a:hover { text-decoration: underline; color: var(--accent-hover); }
  tr:hover { background: var(--surface); }
  td:nth-child(1) { max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td:nth-child(2) { white-space: nowrap; }
  td:nth-child(3) { white-space: nowrap; text-align: center; }
  td:nth-child(4) { font-size: 0.82em; white-space: nowrap; }
  td:nth-child(5), td:nth-child(6) { font-size: 0.82em; white-space: nowrap; }
  td:nth-child(7) { font-size: 0.82em; white-space: nowrap; color: var(--text-muted); }
  td:nth-child(8) { font-size: 0.82em; text-align: left; }
  tr.inactive td { color: var(--text-muted); }
  tr.inactive td a { color: var(--text-muted); }
  tr.inactive td a:hover { color: var(--accent); }
  .sid-cell {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.72em;
    color: var(--text-muted);
    cursor: pointer;
    white-space: nowrap;
  }
  .sid-cell:hover { color: var(--accent); }
  .stop-btn {
    display: inline-block;
    padding: 2px 8px;
    border: 1px solid #c44;
    border-radius: 4px;
    font-size: 0.75em;
    color: #c44;
    cursor: pointer;
    background: none;
    vertical-align: middle;
  }
  .stop-btn:hover { background: #c44; color: #fff; }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { background: var(--accent-hover); }
  th .sort-arrow { margin-left: 4px; font-size: 0.9em; }
  .on-air-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    background: #d97757;
    border-radius: 50%;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .start-btn {
    display: inline-block;
    padding: 2px 8px;
    border: 1px solid var(--accent);
    border-radius: 4px;
    font-size: 0.75em;
    color: var(--accent);
    cursor: pointer;
    background: none;
    vertical-align: middle;
  }
  .start-btn:hover { background: var(--accent); color: #fff; }
  .search-box {
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .search-box input {
    max-width: 400px;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
    font-size: 0.9em;
    outline: none;
  }
  .search-box input:focus { border-color: var(--accent); }
  .search-box button {
    padding: 8px 16px;
    border: 1px solid var(--accent);
    border-radius: 8px;
    background: var(--accent);
    color: #fff;
    font-size: 0.9em;
    cursor: pointer;
  }
  .search-box button:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
  .new-session-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 16px 40px;
    z-index: 100;
    display: flex;
    gap: 12px;
    align-items: flex-end;
  }
  .new-session-bar textarea {
    flex: 1;
    min-height: 60px;
    max-height: 150px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
    font-family: inherit;
    font-size: 0.95em;
    line-height: 1.5;
    resize: vertical;
    outline: none;
  }
  .new-session-bar textarea:focus { border-color: var(--accent); }
  .new-session-bar textarea::placeholder { color: var(--text-muted); }
  .new-session-bar button {
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: #fff;
    font-size: 0.9em;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .new-session-bar button:hover { background: var(--accent-hover); }
  body { padding-bottom: 120px; }
  @media (max-width: 768px) {
    body { padding: 16px; padding-bottom: 100px; }
    .claude-bot-wrap { gap: 12px; margin-bottom: 16px; }
    .claude-bot-wrap h1 { font-size: 1.1em; }
    .claude-bot-svg { width: 40px; height: 35px; }
    .subtitle { margin-bottom: 16px; font-size: 0.85em; }
    .search-box { margin-bottom: 16px; }
    .search-box input { max-width: 100%; flex: 1; }
    table { font-size: 0.85em; }
    th:nth-child(2), td:nth-child(2),
    th:nth-child(5), td:nth-child(5),
    th:nth-child(6), td:nth-child(6),
    th:nth-child(7), td:nth-child(7) { display: none; }
    td:nth-child(1) { max-width: 200px; }
    .start-btn, .stop-btn { font-size: 0.7em; padding: 2px 6px; margin: 0; }
    th, td { padding: 8px 6px; }
    .new-session-bar { padding: 12px 16px; gap: 8px; }
    .new-session-bar textarea { min-height: 44px; font-size: 0.9em; }
    .new-session-bar button { padding: 10px 16px; font-size: 0.85em; }
  }
</style>
</head>
<body>
<div class="claude-bot-wrap">
  <svg class="claude-bot-svg" width="64" height="56" viewBox="0 0 64 56" fill="none" shape-rendering="crispEdges">
    <rect x="0" y="16" width="8" height="8" fill="var(--accent)"/>
    <rect x="56" y="16" width="8" height="8" fill="var(--accent)"/>
    <rect x="12" y="0" width="40" height="8" fill="var(--accent)"/>
    <rect x="8" y="8" width="48" height="24" fill="var(--accent)"/>
    <rect class="eye" x="20" y="14" width="6" height="8" fill="var(--bg)"/>
    <rect class="eye" x="38" y="14" width="6" height="8" fill="var(--bg)"/>
    <rect class="leg1" x="12" y="32" width="8" height="12" fill="var(--accent)"/>
    <rect class="leg2" x="24" y="32" width="8" height="12" fill="var(--accent)"/>
    <rect class="leg3" x="36" y="32" width="8" height="12" fill="var(--accent)"/>
    <rect class="leg4" x="48" y="32" width="8" height="12" fill="var(--accent)"/>
  </svg>
  <h1>Claude Code Session Dashboard</h1>
</div>
<div class="subtitle">%%SESSION_COUNT%% sessions</div>
<div class="search-box">
  <input type="text" id="searchInput" placeholder="Search conversations...">
  <button onclick="goSearch()">Search</button>
</div>
<div style="margin-bottom:16px;">
  <label style="font-size:0.85em;cursor:pointer;color:var(--text-muted);display:flex;align-items:center;gap:4px;">
    <input type="checkbox" id="activeOnly"> Active sessions only
  </label>
  <label style="font-size:0.85em;cursor:pointer;color:var(--text-muted);display:flex;align-items:center;gap:4px;">
    <input type="checkbox" id="showHidden"> Show hidden sessions
  </label>
</div>
<table id="sessionTable">
<thead><tr><th>Session</th><th>ID</th><th>Control</th><th class="sortable" data-col="3" data-type="time">Last active<span class="sort-arrow">&#9660;</span></th><th class="sortable" data-col="4" data-type="text">Start<span class="sort-arrow"></span></th><th class="sortable" data-col="5" data-type="text">End<span class="sort-arrow"></span></th><th class="sortable" data-col="6" data-type="duration">Duration<span class="sort-arrow"></span></th><th class="sortable" data-col="7" data-type="num">Messages<span class="sort-arrow"></span></th></tr></thead>
<tbody>
%%TBODY%%
</tbody>
</table>
<div class="new-session-bar">
  <textarea id="newSessionInput" placeholder="Type a message to start a new session... (Cmd+Enter to send)"></textarea>
  <button id="newSessionBtn" onclick="newSession()">+ New Session</button>
</div>
<script>
(function() {
  function timeAgo(date) {
    var now = new Date();
    var seconds = Math.floor((now - date) / 1000);
    if (seconds < 0) return 'just now';
    if (seconds < 60) return seconds + 's ago';
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + 'm ago';
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + 'h ago';
    var days = Math.floor(hours / 24);
    if (days < 30) return days + 'd ago';
    var months = Math.floor(days / 30);
    if (months < 12) return months + 'mo ago';
    var years = Math.floor(days / 365);
    return years + 'y ago';
  }
  document.querySelectorAll('.time-ago').forEach(function(el) {
    var d = new Date(el.dataset.time);
    if (!isNaN(d)) el.textContent = timeAgo(d);
  });
  document.querySelectorAll('a[data-sid]').forEach(function(a) {
    var saved = localStorage.getItem('title_' + a.dataset.sid);
    if (saved) {
      a.textContent = saved;
      var badge = document.createElement('span');
      badge.textContent = ' (edited)';
      badge.style.cssText = 'font-size:0.8em; color:var(--text-muted); font-weight:400;';
      a.appendChild(badge);
    }
  });

  var input = document.getElementById('searchInput');
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') window.goSearch();
  });
  window.goSearch = function() {
    var q = input.value.trim();
    if (q) window.location.href = 'search.html?q=' + encodeURIComponent(q);
  };

  window.newSession = function() {
    var msg = document.getElementById('newSessionInput').value.trim();
    if (!msg) { alert('Please enter a message.'); return; }
    var btn = document.getElementById('newSessionBtn');
    btn.disabled = true;
    document.getElementById('newSessionInput').disabled = true;
    var dots = 0;
    var baseText = 'Creating';
    btn.textContent = baseText;
    var animInterval = setInterval(function() {
      dots = (dots + 1) % 4;
      btn.textContent = baseText + '.'.repeat(dots + 1);
    }, 500);
    fetch('/new-session?msg=' + encodeURIComponent(msg))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        clearInterval(animInterval);
        if (data.status === 'ok') {
          btn.textContent = 'Session started!';
          document.getElementById('newSessionInput').value = '';
          document.getElementById('newSessionInput').disabled = false;
          setTimeout(function() { btn.textContent = '+ New Session'; btn.disabled = false; }, 2000);
        } else {
          btn.textContent = '+ New Session';
          btn.disabled = false;
          document.getElementById('newSessionInput').disabled = false;
          alert('Failed: ' + (data.message || ''));
        }
      })
      .catch(function() {
        clearInterval(animInterval);
        btn.textContent = '+ New Session';
        btn.disabled = false;
        document.getElementById('newSessionInput').disabled = false;
        alert('Cannot connect to server.');
      });
  };

  document.getElementById('newSessionInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      window.newSession();
    }
  });

  document.querySelectorAll('.sid-cell').forEach(function(cell) {
    cell.style.cursor = 'pointer';
    cell.title = 'Click to copy';
    cell.addEventListener('click', function() {
      var sid = this.dataset.sid;
      var el = this;
      navigator.clipboard.writeText(sid).then(function() {
        var orig = el.textContent;
        el.textContent = 'Copied!';
        setTimeout(function() { el.textContent = orig; }, 5000);
      });
    });
  });

  document.querySelectorAll('#sessionTable tbody tr').forEach(function(row) {
    var sid = row.dataset.sid;
    var cell = row.querySelector('.start-cell');
    if (cell) {
      var btn = document.createElement('button');
      btn.className = 'start-btn';
      btn.textContent = 'Resume';
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        startSession(sid, btn);
      });
      cell.appendChild(btn);

      var stopBtn = document.createElement('button');
      stopBtn.className = 'stop-btn';
      stopBtn.textContent = 'Stop';
      stopBtn.dataset.sid = sid;
      stopBtn.style.display = 'none';
      stopBtn.addEventListener('click', function(e) {
        e.preventDefault();
        stopSession(sid, stopBtn);
      });
      cell.appendChild(stopBtn);
    }
  });

  var _hiddenSet = new Set();

  fetch('/hidden')
    .then(function(r) { return r.json(); })
    .then(function(list) {
      _hiddenSet = new Set(list);
      applyHiddenFilter();
    })
    .catch(function() {});

  function getHidden() { return _hiddenSet; }

  function toggleHide(sid) {
    if (_hiddenSet.has(sid)) {
      _hiddenSet.delete(sid);
    } else {
      _hiddenSet.add(sid);
    }
    fetch('/hidden-update', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Array.from(_hiddenSet))
    }).catch(function() {});
    applyHiddenFilter();
  }

  function applyHiddenFilter() {
    var hidden = getHidden();
    var showHidden = document.getElementById('showHidden').checked;
    var activeOnly = document.getElementById('activeOnly').checked;
    document.querySelectorAll('#sessionTable tbody tr').forEach(function(row) {
      var sid = row.dataset.sid;
      var isHidden = hidden.has(sid);
      var isActive = row.dataset.active === 'true';
      if (isHidden && !showHidden) {
        row.style.display = 'none';
      } else if (activeOnly && !isActive) {
        row.style.display = 'none';
      } else {
        row.style.display = '';
      }
      row.style.opacity = (isHidden && showHidden) ? '0.5' : '';
    });
  }

  applyHiddenFilter();

  document.getElementById('showHidden').addEventListener('change', applyHiddenFilter);

  function stopSession(sid, btn) {
    if (!confirm('Stop this session?')) return;
    btn.textContent = 'Stopping...';
    btn.disabled = true;
    fetch('/stop/' + sid)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status === 'ok') {
          btn.textContent = 'Stopped';
          btn.style.background = '#888';
          btn.style.color = '#fff';
          btn.style.borderColor = '#888';
          var row = btn.closest('tr');
          row.classList.add('inactive');
          row.dataset.active = '';
          var sb = row.querySelector('.stop-btn');
          if (sb) sb.style.display = 'none';
          var ab = row.querySelector('.start-btn');
          if (ab) { ab.style.display = ''; ab.textContent = 'Resume'; ab.disabled = false; }
        } else {
          btn.textContent = 'Failed';
          alert('Stop failed: ' + (data.message || ''));
        }
      })
      .catch(function() {
        btn.textContent = 'Stop';
        btn.disabled = false;
        alert('Cannot connect to server.');
      });
  }

  function startSession(sid, btn) {
    btn.textContent = 'Starting...';
    btn.disabled = true;
    fetch('/start/' + sid)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status === 'ok') {
          btn.textContent = 'Active';
          btn.style.background = 'var(--green, #788c5d)';
          btn.style.color = '#fff';
          btn.style.borderColor = 'var(--green, #788c5d)';
          var row = btn.closest('tr');
          row.classList.remove('inactive');
          row.dataset.active = 'true';
          btn.style.display = 'none';
          var sb = row.querySelector('.stop-btn');
          if (sb) sb.style.display = '';
        } else {
          btn.textContent = 'Failed';
          alert('Start failed: ' + (data.message || ''));
        }
      })
      .catch(function() {
        btn.textContent = 'Resume';
        btn.disabled = false;
        alert('Cannot connect to server.');
      });
  }

  var _lastActiveJSON = '';

  function updateActiveStatus() {
    fetch('/active')
      .then(function(r) { return r.json(); })
      .then(function(activeMap) {
        var newJSON = JSON.stringify(activeMap);
        if (newJSON === _lastActiveJSON) return;
        _lastActiveJSON = newJSON;

        document.querySelectorAll('#sessionTable tbody tr').forEach(function(row) {
          var sid = row.dataset.sid;
          var info = activeMap[sid];
          if (info) {
            row.dataset.active = 'true';
            row.classList.remove('inactive');
            var sb = row.querySelector('.stop-btn');
            if (sb) sb.style.display = '';
            var ab = row.querySelector('.start-btn');
            if (ab) ab.style.display = 'none';
          } else {
            row.dataset.active = '';
            row.classList.add('inactive');
            var sb = row.querySelector('.stop-btn');
            if (sb) sb.style.display = 'none';
            var ab = row.querySelector('.start-btn');
            if (ab) ab.style.display = '';
          }
        });

        applyHiddenFilter();
      })
      .catch(function() {});
  }

  document.querySelectorAll('#sessionTable tbody tr').forEach(function(row) {
    row.classList.add('inactive');
  });
  updateActiveStatus();
  setInterval(updateActiveStatus, 5000);

  document.getElementById('activeOnly').addEventListener('change', applyHiddenFilter);

  document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
      updateActiveStatus();
      document.querySelectorAll('.time-ago').forEach(function(el) {
        var d = new Date(el.dataset.time);
        if (!isNaN(d)) el.textContent = timeAgo(d);
      });
    }
  });

  // Pull-to-refresh (for mobile home screen web apps)
  (function() {
    var startY = 0;
    var triggered = false;
    var indicator = document.createElement('div');
    indicator.style.cssText = 'position:fixed;top:0;left:0;right:0;text-align:center;padding:12px;background:var(--accent);color:#fff;font-size:0.85em;z-index:9999;transform:translateY(-100%);transition:transform 0.2s;';
    indicator.textContent = 'Pull to refresh';
    document.body.appendChild(indicator);

    document.addEventListener('touchstart', function(e) {
      if (window.scrollY === 0) {
        startY = e.touches[0].clientY;
        triggered = false;
      }
    }, { passive: true });

    document.addEventListener('touchmove', function(e) {
      if (window.scrollY > 0) return;
      var diff = e.touches[0].clientY - startY;
      if (diff > 10 && diff <= 80) {
        indicator.style.transform = 'translateY(0)';
        indicator.textContent = 'Pull to refresh';
        triggered = false;
      } else if (diff > 80) {
        indicator.textContent = 'Release to refresh';
        triggered = true;
      }
    }, { passive: true });

    document.addEventListener('touchend', function() {
      if (triggered) {
        indicator.textContent = 'Refreshing...';
        fetch('/refresh', { signal: AbortSignal.timeout(5000) })
          .then(function() {
            indicator.textContent = 'Done';
            setTimeout(function() {
              window.location.reload();
            }, 300);
          })
          .catch(function() {
            window.location.reload();
          });
      } else {
        indicator.style.transform = 'translateY(-100%)';
      }
      triggered = false;
    });
  })();

  // Table sorting
  var currentSort = { col: 3, asc: false };
  var tbody = document.querySelector('#sessionTable tbody');

  function parseDuration(s) {
    if (!s) return 0;
    var total = 0;
    var m;
    m = s.match(/(\\d+)d/); if (m) total += parseInt(m[1]) * 86400;
    m = s.match(/(\\d+)h/); if (m) total += parseInt(m[1]) * 3600;
    m = s.match(/(\\d+)m/); if (m) total += parseInt(m[1]) * 60;
    m = s.match(/(\\d+)s/); if (m) total += parseInt(m[1]);
    return total;
  }

  function sortTable(col, type) {
    var asc = currentSort.col === col ? !currentSort.asc : false;
    currentSort = { col: col, asc: asc };
    var rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort(function(a, b) {
      var cellA = a.children[col];
      var cellB = b.children[col];
      var va, vb;
      if (type === 'time') {
        va = cellA.dataset.time || '';
        vb = cellB.dataset.time || '';
      } else if (type === 'num') {
        va = parseInt(cellA.textContent) || 0;
        vb = parseInt(cellB.textContent) || 0;
        return asc ? va - vb : vb - va;
      } else if (type === 'duration') {
        va = parseDuration(cellA.textContent);
        vb = parseDuration(cellB.textContent);
        return asc ? va - vb : vb - va;
      } else {
        va = cellA.textContent.trim();
        vb = cellB.textContent.trim();
      }
      if (va < vb) return asc ? -1 : 1;
      if (va > vb) return asc ? 1 : -1;
      return 0;
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
    document.querySelectorAll('th.sortable .sort-arrow').forEach(function(el) { el.textContent = ''; });
    var th = document.querySelector('th.sortable[data-col="' + col + '"] .sort-arrow');
    if (th) th.textContent = asc ? '\\u25B2' : '\\u25BC';
  }

  document.querySelectorAll('th.sortable').forEach(function(th) {
    th.addEventListener('click', function() {
      sortTable(parseInt(this.dataset.col), this.dataset.type);
    });
  });
})();
</script>
<script>
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(function() {});
}
</script>
</body>
</html>"""

    index_html = INDEX_TEMPLATE.replace('%%SESSION_COUNT%%', str(len(sessions))).replace('%%TBODY%%', tbody_content)

    with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index_html)


def build_search_index(sessions):
    """Generate the search page with server-side search API."""

    search_html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Search - Claude Code Sessions</title>
<style>
  :root {
    --bg: #faf9f5;
    --surface: #fff;
    --surface2: #f0efe8;
    --text: #141413;
    --text-muted: #b0aea5;
    --border: #e8e6dc;
    --accent: #d97757;
    --accent-hover: #c4623f;
    --highlight: #fef3cd;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #141413;
      --surface: #1e1e1c;
      --surface2: #2a2a27;
      --text: #faf9f5;
      --text-muted: #b0aea5;
      --border: #2a2a27;
      --accent: #d97757;
      --accent-hover: #e8896b;
      --highlight: #4a3f20;
    }
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 40px;
  }
  h1 { margin-bottom: 8px; }
  .nav { margin-bottom: 24px; }
  .nav a { color: var(--accent); text-decoration: none; font-size: 0.9em; }
  .nav a:hover { text-decoration: underline; }
  .search-box {
    width: 100%; max-width: 600px; padding: 12px 16px; font-size: 1em;
    border: 1px solid var(--border); border-radius: 8px;
    background: var(--surface); color: var(--text); margin-bottom: 24px; outline: none;
  }
  .search-box:focus { border-color: var(--accent); }
  .status { color: var(--text-muted); font-size: 0.9em; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
  th {
    background: var(--accent); color: #fff; font-size: 0.75em;
    text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap;
  }
  td a { color: var(--accent); text-decoration: none; }
  td a:hover { text-decoration: underline; color: var(--accent-hover); }
  tr.result-row:hover { background: var(--surface); }
  td:nth-child(1) { max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td:nth-child(2), td:nth-child(3) { font-size: 0.82em; white-space: nowrap; }
  td:nth-child(4) { font-size: 0.82em; white-space: nowrap; color: var(--text-muted); }
  td:nth-child(5) { font-size: 0.82em; text-align: center; }
  td:nth-child(6) { font-size: 0.82em; text-align: center; color: var(--accent); font-weight: 600; }
  .snippet-row td {
    padding: 8px 12px 14px; font-size: 0.85em; line-height: 1.5;
    color: var(--text-muted); border-bottom: 2px solid var(--border);
  }
  .snippet-row mark {
    background: var(--highlight); color: var(--text); padding: 1px 3px; border-radius: 2px;
  }
  @media (max-width: 768px) {
    body { padding: 16px; }
    td:nth-child(2), td:nth-child(3), td:nth-child(4) { display: none; }
    th:nth-child(2), th:nth-child(3), th:nth-child(4) { display: none; }
    td:nth-child(1) { max-width: 200px; }
  }
</style>
</head>
<body>
<h1>Search Sessions</h1>
<div class="nav"><a href="index.html">&larr; All sessions</a></div>
<input type="text" class="search-box" id="searchInput" placeholder="Enter search query (min 2 chars)..." autofocus>
<div class="status" id="status">Enter a search query (2+ characters)</div>
<div id="results"></div>
<script>
function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function timeAgo(date) {
  var now = new Date();
  var seconds = Math.floor((now - date) / 1000);
  if (seconds < 0) return 'just now';
  if (seconds < 60) return seconds + 's ago';
  var minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + 'm ago';
  var hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + 'h ago';
  var days = Math.floor(hours / 24);
  if (days < 30) return days + 'd ago';
  var months = Math.floor(days / 30);
  return months + 'mo ago';
}
var debounceTimer;
document.getElementById('searchInput').addEventListener('input', function() {
  clearTimeout(debounceTimer);
  var q = this.value.trim();
  if (q.length < 2) {
    document.getElementById('results').innerHTML = '';
    document.getElementById('status').textContent = 'Enter a search query (2+ characters)';
    return;
  }
  document.getElementById('status').textContent = 'Searching...';
  debounceTimer = setTimeout(function() { doSearch(q); }, 300);
});
function doSearch(query) {
  fetch('/search?q=' + encodeURIComponent(query))
    .then(function(r) { return r.json(); })
    .then(function(matches) {
      var total = matches.reduce(function(a, b) { return a + b.count; }, 0);
      document.getElementById('status').textContent = total + ' matches in ' + matches.length + ' sessions';
      var html = '<table><thead><tr><th>Session</th><th>Start</th><th>End</th><th>Duration</th><th>Messages</th><th>Matches</th></tr></thead><tbody>';
      matches.forEach(function(m) {
        var endIso = m.end_date ? m.end_date.replace(' ', 'T') + ':00+09:00' : '';
        var ago = endIso ? timeAgo(new Date(endIso)) : '';
        var snippet = escapeHtml(m.snippet);
        var ql = query.toLowerCase();
        var sl = snippet.toLowerCase();
        var idx = sl.indexOf(ql);
        if (idx !== -1) {
          snippet = snippet.substring(0, idx) + '<mark>' + snippet.substring(idx, idx + query.length) + '</mark>' + snippet.substring(idx + query.length);
        }
        html += '<tr class="result-row"><td><a href="' + m.id + '.html">' + escapeHtml(m.title) + '</a></td>';
        html += '<td>' + escapeHtml(m.start_date) + '</td><td>' + escapeHtml(m.end_date) + '</td>';
        html += '<td>' + escapeHtml(m.duration) + '</td><td>' + m.msg_count + '</td>';
        html += '<td>' + m.count + '</td></tr>';
        html += '<tr class="snippet-row"><td colspan="6">' + snippet + '</td></tr>';
      });
      html += '</tbody></table>';
      document.getElementById('results').innerHTML = html;
    })
    .catch(function() {
      document.getElementById('status').textContent = 'Search failed - cannot connect to server';
    });
}
(function() {
  var params = new URLSearchParams(window.location.search);
  var q = params.get('q');
  if (q) {
    document.getElementById('searchInput').value = q;
    doSearch(q);
  }
})();
</script>
</body>
</html>"""

    with open(os.path.join(OUTPUT_DIR, 'search.html'), 'w', encoding='utf-8') as f:
        f.write(search_html)

    return []


def collect_existing_sessions():
    """Collect session metadata from existing HTML files."""
    sessions = []
    existing_htmls = glob.glob(os.path.join(OUTPUT_DIR, '*.html'))
    for eh in existing_htmls:
        basename = Path(eh).stem
        if basename in ('index', 'search'):
            continue
        try:
            with open(eh, 'r', encoding='utf-8') as f:
                content = f.read(10000)
            title_match = re.search(r'<title>(.+?)</title>', content, re.DOTALL)
            meta_match = re.search(r'class="meta">(.+?)</div>', content, re.DOTALL)
            if title_match and meta_match:
                meta_text = meta_match.group(1)
                parts = meta_text.split('|')

                time_part = parts[1].strip() if len(parts) > 1 else ''
                msg_count_match = re.search(r'(\d+) messages', meta_text)
                msg_count = int(msg_count_match.group(1)) if msg_count_match else 0

                arrow_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*(?:→|&rarr;)\s*(\S+)', time_part)
                if arrow_match:
                    start_date = arrow_match.group(1)
                    end_time = arrow_match.group(2)
                    if re.match(r'^\d{2}:\d{2}$', end_time):
                        end_date = start_date[:10] + ' ' + end_time
                    else:
                        end_date = end_time
                    dur_match = re.search(r'\((.+?)\)', time_part)
                    duration = dur_match.group(1) if dur_match else ''
                else:
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', time_part)
                    start_date = date_match.group(1) if date_match else ''
                    end_date = start_date
                    duration = ''

                sessions.append({
                    'session_id': basename,
                    'title': title_match.group(1),
                    'start_date': start_date,
                    'end_date': end_date,
                    'duration': duration,
                    'msg_count': msg_count,
                    'path': eh
                })
        except Exception:
            pass
    return sessions


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    jsonl_files = []
    for root, dirs, files in os.walk(PROJECTS_DIR):
        for fname in files:
            if fname.endswith('.jsonl'):
                jsonl_files.append(os.path.join(root, fname))

    # --rename command
    if len(sys.argv) >= 4 and sys.argv[1] == '--rename':
        rename_sid = sys.argv[2]
        rename_title = sys.argv[3]
        summaries_cache = load_summaries()
        existing = summaries_cache.get(rename_sid, {})
        if isinstance(existing, str):
            existing = {'title': existing, 'msg_count': 0}
        existing['title'] = rename_title
        summaries_cache[rename_sid] = existing
        save_summaries(summaries_cache)
        matched = [f for f in jsonl_files if rename_sid in os.path.basename(f)]
        if matched:
            result = convert_session(matched[0], summaries_cache=summaries_cache)
            if result:
                all_sessions = collect_existing_sessions()
                all_sessions = [s for s in all_sessions if s['session_id'] != rename_sid]
                all_sessions.append(result)
                build_search_index(all_sessions)
                build_index(all_sessions)
                print(f"Renamed: \"{rename_title}\"")
        else:
            print(f"Updated summaries.json (JSONL not found, will apply on next full convert)")
        return

    force = False
    if len(sys.argv) > 1:
        if sys.argv[1] == '--force':
            force = True
        elif sys.argv[1] != '--rename':
            session_id = sys.argv[1]
            jsonl_files = [f for f in jsonl_files if session_id in os.path.basename(f)]
            force = True

    summaries_cache = load_summaries()
    initial_count = len(summaries_cache)

    converted = []
    skipped = 0
    for jf in jsonl_files:
        sid = Path(jf).stem
        if sid.startswith('agent-'):
            continue

        if not force:
            html_path = os.path.join(OUTPUT_DIR, f"{sid}.html")
            if os.path.isfile(html_path):
                jsonl_size = os.path.getsize(jf)
                try:
                    with open(html_path, 'r', encoding='utf-8') as hf:
                        first_line = hf.read(500)
                    size_match = re.search(r'data-jsonl-size="(\d+)"', first_line)
                    if size_match and int(size_match.group(1)) == jsonl_size:
                        skipped += 1
                        continue
                except Exception:
                    pass

        try:
            result = convert_session(jf, summaries_cache=summaries_cache)
            if result:
                converted.append(result)
                print(f"  Converted: {result['title'][:50]}  ({result['start_date']} -> {result['end_date']})")
        except Exception as e:
            print(f"  Error: {os.path.basename(jf)}: {e}")

    if skipped > 0:
        print(f"  Skipped {skipped} unchanged sessions")

    save_summaries(summaries_cache)
    new_count = len(summaries_cache) - initial_count
    if new_count > 0:
        print(f"  Generated {new_count} new summaries")

    all_sessions = collect_existing_sessions()
    converted_ids = {s['session_id'] for s in converted}
    all_sessions = [s for s in all_sessions if s['session_id'] not in converted_ids]
    all_sessions.extend(converted)

    if all_sessions:
        build_search_index(all_sessions)
        build_index(all_sessions)
        print(f"\nIndex updated: {len(all_sessions)} sessions -> {OUTPUT_DIR}")
    elif converted:
        print(f"\n{len(converted)} sessions converted")
    else:
        print("No sessions to convert.")


if __name__ == '__main__':
    main()
