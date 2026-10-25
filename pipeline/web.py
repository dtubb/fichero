"""The page (pipeline.dashboard-minimal): one HTML file plus a JSON API on 127.0.0.1 only, over `core.API`. It
answers three questions at a glance — what is happening now, what is done, what needs me — in words: a "Now" line,
one status sentence per item (details behind a disclosure), an open-only queue with a collapsed Done list.
Host must be 127.0.0.1:<port> or localhost:<port> on every request (DNS rebinding), every POST needs the token
minted at launch (embedded in the page) AND an Origin on that same host list. Worker text (queue options, reports)
is rendered through data attributes and textContent, never into JS or HTML.
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
#now{font-size:17px;margin:10px 0 4px}pre{white-space:pre-wrap;margin:0;font-size:13px}details summary{cursor:pointer;color:var(--muted)}code{font-size:13px}
</style></head><body>
<h1>%NAME% pipeline</h1>
<div class="muted">This page shows the runner's own items. GitHub specs, milestones and issues come in Stage 1.</div>
<p id="now">loading…</p><div class="muted" id="meta"></div><div id="paused"></div>
<h2>Items</h2><table id="items"><thead><tr><th>Item</th><th>Status</th><th>Started</th><th>Last change</th><th>Cost</th><th>Details</th></tr></thead><tbody></tbody></table>
<h2>Workers</h2><table id="workers"><thead><tr><th>Window</th><th>Task</th><th>Model</th><th>State</th><th>Cost</th><th>Last said</th><th>Tell</th></tr></thead><tbody></tbody></table>
<h2 id="queue-h">Needs you</h2><table id="queue"><thead><tr><th>When</th><th>Kind</th><th>Question</th><th>Answer</th></tr></thead><tbody></tbody></table>
<details id="done"><summary>Done</summary><table id="queue-done"><thead><tr><th>When</th><th>Kind</th><th>Was</th></tr></thead><tbody></tbody></table></details>
<h2>Point at a milestone</h2><form data-cmd="point"><input name="milestone" placeholder="milestone name" size="40"> <button>Point</button> <span class="muted" id="point"></span></form>
<form data-cmd="pause"><button>Pause all</button></form><form data-cmd="resume"><button>Resume</button></form>
<h2>File a bug</h2><form data-cmd="file_bug">
<input name="title" placeholder="title" size="60"><br><textarea name="text" rows="3" cols="70" placeholder="what was seen, what was expected, the test path"></textarea><br>
<input name="milestone" placeholder="milestone (optional)"> <button>File</button></form>
<script>
const TOKEN=%TOKEN%;
// Every piece of worker or issue text goes through text nodes or data attributes: nothing is built into HTML or JS.
const el=(tag,attrs,...kids)=>{const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(k.startsWith('data-'))e.setAttribute(k,v);else if(k==='class')e.className=v;else e[k]=v}
 for(const k of kids){e.append(k instanceof Node?k:document.createTextNode(k??''))}return e};
const pre=t=>el('pre',{},t);const hhmm=ts=>ts?ts.slice(11,16):'—';const short=s=>(s||'').slice(0,9);
async function cmd(name,args){const r=await fetch('/api/'+name,{method:'POST',headers:{'content-type':'application/json','x-token':TOKEN},body:JSON.stringify(args)});
 const j=await r.json();alert(JSON.stringify(j,null,1));refresh()}
function fill(id,rows){const b=document.querySelector('#'+id+' tbody');b.replaceChildren(...rows)}
async function refresh(){const s=await (await fetch('/api/state')).json();const m=s.machine||{};const nq=Object.keys(s.queue).length;
 document.getElementById('now').replaceChildren(s.now,' ',el('a',{href:'#queue-h'},`Needs you: ${nq}`));
 document.getElementById('meta').textContent=`API spend today $${(s.spend_today||0).toFixed(2)} of the $${(s.daily_cap||0).toFixed(2)} daily cap · ${m.free_mb} MB free, pressure ${m.pressure}, load ${m.load1} · ${new Date().toLocaleTimeString()}`;
 document.getElementById('paused').replaceChildren(...(s.paused?[el('p',{class:'paused'},'PAUSED: nothing new starts until Resume.')]:[]));
 document.getElementById('point').textContent=s.point?'pointed at: '+s.point:'';
 document.getElementById('queue-h').textContent=`Needs you (${nq})`;
 fill('items',Object.values(s.items).map(i=>{const first=(i.history[0]||'').slice(0,19),last=(i.history[i.history.length-1]||'').slice(0,19);
  const checks=(i.checks||[]).map(c=>`${c.ok?'✓':'✗'} ${c.name} ${c.seconds}s`).join('\\n');
  const verdicts=(i.verdicts||[]).map(v=>`${v.verdict} by ${v.by} at ${short(v.sha)}`).join('\\n');
  return el('tr',{},el('td',{},el('b',{},i.key),el('br'),i.title,el('br'),el('span',{class:'muted'},'task '+i.task)),
   el('td',{class:'s-'+i.state},i.summary+(s.stuck.includes(i.key)?' ⚠ stuck':'')),el('td',{},hhmm(first)),el('td',{},hhmm(last)),
   el('td',{},'$'+(i.cost_usd||0).toFixed(2)),
   el('td',{},el('details',{},el('summary',{},`${(i.checks||[]).length} checks, ${(i.verdicts||[]).length} verdicts`),
     el('div',{},el('b',{},'Checks at '+short(i.sha)),pre(checks||'none yet')),el('div',{},el('b',{},'Verdict history'),pre(verdicts||'none yet')),
     el('div',{},el('b',{},'History'),pre((i.history||[]).map(h=>hhmm(h)+' '+h.slice(20)).join('\\n'))))))}));
 fill('workers',Object.values(s.workers).map(w=>{const t=(s.tasks||{})[w.task]||{};return el('tr',{},el('td',{},w.window),el('td',{},w.task),el('td',{},w.model),
  el('td',{},w.idle_text+(w.undelivered?' ⚠ message not delivered':'')),
  el('td',{},`$${(t.cost_usd||0).toFixed(2)} this task · ${t.issues_done||0} done · $${(t.cost_per_issue||0).toFixed(2)} per issue`),el('td',{},w.last_said||'—'),
  el('td',{},el('form',{'data-cmd':'tell','data-window':w.window},el('input',{name:'text',size:28}),el('button',{},'Tell'))))}));
 fill('queue',Object.values(s.queue).map(q=>el('tr',{},el('td',{class:'muted'},hhmm(q.ts)),el('td',{},q.kind),
  el('td',{},pre(q.text),...(q.options||[]).map(o=>el('button',{'data-answer':q.id,'data-text':o},o))),
  el('td',{},el('form',{'data-cmd':'answer','data-qid':q.id},el('input',{name:'text',size:24}),el('button',{},'Answer'))))));
 fill('queue-done',Object.values(s.queue_done||{}).map(q=>el('tr',{},el('td',{class:'muted'},hhmm(q.ts)),el('td',{},q.kind),el('td',{},pre(q.text)))));
 document.querySelector('#done summary').textContent=`Done (${Object.keys(s.queue_done||{}).length})`;}
document.addEventListener('submit',ev=>{const f=ev.target.closest('form[data-cmd]');if(!f)return;ev.preventDefault();
 const args={...f.dataset};delete args.cmd;for(const i of f.querySelectorAll('input,textarea'))args[i.name]=i.value||null;cmd(f.dataset.cmd,args)});
document.addEventListener('click',ev=>{const b=ev.target.closest('button[data-answer]');if(!b)return;cmd('answer',{qid:b.dataset.answer,text:b.dataset.text})});
refresh();setInterval(refresh,4000);
</script></body></html>"""


def allowed_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in allowed_hosts(self.server.server_address[1])

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b'{"error":"host refused"}')
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
        if not self._host_ok() or self.headers.get("x-token") != TOKEN or not origin \
                or origin.split("//", 1)[-1] not in allowed_hosts(self.server.server_address[1]):
            return self._send(403, b'{"error":"host, token or origin refused"}')
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
