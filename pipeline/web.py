"""The page (pipeline.dashboard-minimal): one HTML file plus a JSON API on 127.0.0.1 only, over `core.API`.
Every POST needs the token minted at launch (embedded in the page) and a same-origin Origin header.
Run: python -m pipeline serve [--port 8765]."""
from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline import core

COMMANDS = ("tell", "answer", "point", "pause", "resume", "file_bug", "verdict")  # the page's commands = API entries
TOKEN = secrets.token_urlsafe(24)

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>%NAME% pipeline</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{color-scheme:light dark;--line:#ccc8;--muted:#777}body{font:15px/1.45 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px}table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500}
.s-coding{color:#b47d00}.s-checked,.s-reviewed{color:#2a7a2a}.s-failed,.s-needs-maintainer,.s-rate-limited{color:#b0302a}
.muted{color:var(--muted)}input,textarea,select,button{font:inherit}form{margin:6px 0}.paused{background:#fde;padding:6px 10px;border-radius:6px}
pre{white-space:pre-wrap;margin:0;font-size:13px}
</style></head><body>
<h1>%NAME% pipeline</h1><div class="muted" id="meta">loading…</div><div id="paused"></div>
<h2>Items</h2><table id="items"><thead><tr><th>#</th><th>Title</th><th>State</th><th>Checks</th><th>Verdict</th><th>Cost</th><th>History</th></tr></thead><tbody></tbody></table>
<h2>Workers</h2><table id="workers"><thead><tr><th>Window</th><th>Task</th><th>Model</th><th>Idle</th><th>Cost</th><th>Last said</th><th>Tell</th></tr></thead><tbody></tbody></table>
<h2>Queue</h2><table id="queue"><thead><tr><th>When</th><th>Kind</th><th>Question</th><th>Answer</th></tr></thead><tbody></tbody></table>
<h2>Point at a milestone</h2><form onsubmit="return cmd('point',{milestone:this.milestone.value})"><input name="milestone" placeholder="milestone name" size="40"> <button>Point</button> <span class="muted" id="point"></span></form>
<form onsubmit="return cmd('pause',{})"><button>Pause all</button></form><form onsubmit="return cmd('resume',{})"><button>Resume</button></form>
<h2>File a bug</h2><form onsubmit="return cmd('file_bug',{title:this.title.value,text:this.text.value,milestone:this.milestone.value||null})">
<input name="title" placeholder="title" size="60"><br><textarea name="text" rows="3" cols="70" placeholder="what was seen, what was expected, the test path"></textarea><br>
<input name="milestone" placeholder="milestone (optional)"> <button>File</button></form>
<script>
const TOKEN=%TOKEN%;const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function cmd(name,args){const r=await fetch('/api/'+name,{method:'POST',headers:{'content-type':'application/json','x-token':TOKEN},body:JSON.stringify(args)});
 const j=await r.json();alert(JSON.stringify(j,null,1));refresh();return false}
function rows(id,html){document.querySelector('#'+id+' tbody').innerHTML=html}
async function refresh(){const s=await (await fetch('/api/state')).json();const m=s.machine||{};
 document.getElementById('meta').textContent=`${Object.keys(s.items).length} items · ${Object.keys(s.workers).length} workers · ${Object.keys(s.queue).length} queued · ${m.free_mb} MB free, pressure ${m.pressure}, load ${m.load1} · ${new Date().toLocaleTimeString()}`;
 document.getElementById('paused').innerHTML=s.paused?'<p class="paused">PAUSED: nothing new starts until Resume.</p>':'';
 document.getElementById('point').textContent=s.point?'pointed at: '+s.point:'';
 rows('items',Object.values(s.items).map(i=>`<tr><td>#${i.issue}</td><td>${esc(i.title)}<br><span class="muted">${esc(i.task)}</span></td><td class="s-${i.state}">${i.state}${s.stuck.includes(String(i.issue))?' ⚠ stuck':''}</td>
  <td>${(i.checks||[]).map(c=>`${c.ok?'✓':'✗'} ${esc(c.name)} ${c.seconds}s`).join('<br>')}</td><td>${(i.verdicts||[]).map(v=>`${esc(v.verdict)} by ${esc(v.by)} @${(v.sha||'').slice(0,7)}`).join('<br>')}</td>
  <td>$${(i.cost_usd||0).toFixed(2)}</td><td><pre>${esc((i.history||[]).slice(-4).join('\\n'))}</pre></td></tr>`).join(''));
 rows('workers',Object.values(s.workers).map(w=>`<tr><td>${esc(w.window)}</td><td>${esc(w.task)}</td><td>${esc(w.model)}</td><td>${w.idle===true?'idle':w.idle===false?'busy':'—'}</td><td>$${w.cost_usd}</td><td><pre>${esc(w.last_text)}</pre></td>
  <td><form onsubmit="return cmd('tell',{window:'${esc(w.window)}',text:this.t.value})"><input name="t" size="28"><button>Tell</button></form></td></tr>`).join(''));
 rows('queue',Object.values(s.queue).map(q=>`<tr><td class="muted">${esc(q.ts)}</td><td>${esc(q.kind)}</td><td><pre>${esc(q.text)}</pre>${(q.options||[]).map(o=>`<button onclick="cmd('answer',{qid:'${q.id}',text:'${esc(o)}'})">${esc(o)}</button>`).join(' ')}</td>
  <td><form onsubmit="return cmd('answer',{qid:'${q.id}',text:this.t.value})"><input name="t" size="24"><button>Answer</button></form></td></tr>`).join(''));}
refresh();setInterval(refresh,4000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            html = PAGE.replace("%TOKEN%", json.dumps(TOKEN)).replace("%NAME%", core.cfg()["name"])
            self._send(200, html.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, json.dumps(core.API["status"](), default=str).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        name = self.path.removeprefix("/api/")
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        if self.headers.get("x-token") != TOKEN or (origin and origin.split("//", 1)[-1] != host):
            return self._send(403, b'{"error":"token or origin refused"}')
        if name not in COMMANDS:
            return self._send(404, b'{"error":"no such command"}')
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        try:
            self._send(200, json.dumps(core.API[name](**body), default=str).encode())
        except Exception as e:  # noqa: BLE001 - the page shows the error; nothing moved
            self._send(400, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())


def serve(port: int = 8765, block: bool = True) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"pipeline page: http://127.0.0.1:{httpd.server_address[1]}/  (token in the page; POSTs need it)", flush=True)
    if block:
        httpd.serve_forever()
    else:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
