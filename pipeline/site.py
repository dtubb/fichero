"""The site's pages (pipeline.dashboard-pages): server-rendered HTML with plain links and filters in the query
string, one function per page, over the same state the runner page reads. Every piece of text from GitHub, a spec or a
worker is escaped. Each page reloads itself every `REFRESH` seconds, so it stays current without a script.
GitHub data comes through gh.read (cached); when it fails the page says so and still shows the rest."""
from __future__ import annotations

import re
from html import escape as e
from pathlib import Path
from urllib.parse import quote

from pipeline import core, gh

REFRESH = 15
TAG = re.compile(r"^- `[a-z0-9_.-]+` \[([A-Z]+)", re.MULTILINE)
STATUS = re.compile(r"\*\*Status: (\w+)")
NAV = (("/", "Runner"), ("/specs", "Specs"), ("/milestones", "Milestones"), ("/issues", "Issues"), ("/next", "Next"), ("/items", "Items and cost"))
STYLE = ("body{font:15px/1.45 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px}nav a{margin-right:14px}"
         "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #ccc8;vertical-align:top}"
         "th{color:#777;font-weight:500}.bad{color:#b0302a}.ok{color:#2a7a2a}.muted{color:#777}.bar{background:#8883;height:8px;border-radius:4px}"
         ".bar i{display:block;height:8px;border-radius:4px;background:#2a7a2a}")


def page(title: str, body: str) -> str:
    nav = "".join(f'<a href="{h}">{e(t)}</a>' for h, t in NAV)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="{REFRESH}">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(core.cfg()["name"])} {e(title)}</title>'
            f"<style>{STYLE}</style></head><body><nav>{nav}</nav><h1>{e(title)}</h1>{body}</body></html>")


def table(head: list[str], rows: list[list[str]]) -> str:
    """Cells are HTML the caller already escaped."""
    th = "".join(f"<th>{e(h)}</th>" for h in head)
    return f"<table><thead><tr>{th}</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>"


def bar(done: float, total: float) -> str:
    pct = round(100 * done / total) if total else 0
    return f'<div class="bar"><i style="width:{pct}%"></i></div><span class="muted">{pct}%</span>'


def github(*args) -> tuple[list, str]:
    try:
        return gh.read(*args), ""
    except Exception as err:  # noqa: BLE001 - offline or no gh: say so, show the rest
        return [], f'<p class="bad">GitHub unavailable: {e(str(err)[:200])}</p>'


def specs_page(q: dict) -> str:
    c = core.cfg()
    root = Path(c["repo"]["path"]) / c["repo"]["specs"]
    rows = []
    for p in sorted(root.rglob("*.md")):
        text = p.read_text()
        tags = {}
        for t in TAG.findall(text):
            tags[t] = tags.get(t, 0) + 1
        if not tags:
            continue
        status = next(iter(STATUS.findall("\n".join(text.splitlines()[:20]))), "—")
        ms = re.search(r"Milestone: (\S+)", "\n".join(text.splitlines()[:20]))
        rows.append([e(str(p.relative_to(root))), e(status), e(ms.group(1) if ms else "—"),
                     " · ".join(f"{e(t)} {n}" for t, n in sorted(tags.items())), bar(tags.get("OK", 0), sum(tags.values()))])
    return page("Specs", "<p class=muted>Behaviours by status tag; the bar is OK over all.</p>" +
                table(["Spec", "Status", "Milestone", "Behaviours", "Built"], rows))


def milestones_page(q: dict) -> str:
    s = core.state()
    ms, err = github("api", "repos/{owner}/{repo}/milestones?state=all&per_page=100")
    coding = {}
    for it in s["items"].values():
        if it["state"] in ("coding", "queued") and it.get("start_args", {}).get("milestone"):
            coding.setdefault(it["start_args"]["milestone"], []).append(f"#{core._n(it['key'])}")
    rows = [[e(m["title"]) + (" ◀ pointed" if s["point"] == m["title"] else ""), e(m["state"]), f"{m['closed_issues']} of {m['open_issues'] + m['closed_issues']}",
             bar(m["closed_issues"], m["open_issues"] + m["closed_issues"]), e(", ".join(coding.get(m["title"], [])) or "—"), e((m.get("due_on") or "—")[:10])]
            for m in sorted(ms, key=lambda m: (m["state"] != "open", m["title"]))]
    return page("Milestones", err + table(["Milestone", "State", "Closed", "Progress", "Being coded", "Due"], rows))


def issues_page(q: dict) -> str:
    c, s = core.cfg(), core.state()
    state = q.get("state", "open")
    found, err = github("issue", "list", "--state", state if state in ("open", "closed") else "all", "--limit", "300",
                        "--json", "number,title,labels,milestone,author,state,url,closedAt")
    runner = {core._n(k): it["state"] for k, it in s["items"].items()}
    out = []
    for d in found:
        i = gh._slim(d)
        if q.get("milestone") and i["milestone"] != q["milestone"] or q.get("label") and q["label"] not in i["labels"]:
            continue
        if q.get("claimed") and c["labels"]["claimed"] not in i["labels"] or q.get("from_user") and c["labels"]["from_user"] not in i["labels"]:
            continue
        out.append([f'<a href="{e(i["url"])}">#{i["number"]}</a>', e(i["title"]), e(i["state"].lower()), e(i["milestone"] or "—"),
                    e(", ".join(i["labels"])), e(runner.get(i["number"], "—"))])
    links = " · ".join(f'<a href="/issues?state={st}">{st}</a>' for st in ("open", "closed", "all")) + \
            f' · <a href="/issues?state={e(state)}&label={quote(c["labels"]["bug"])}">bugs</a>' + \
            f' · <a href="/issues?state={e(state)}&from_user=1">from you</a> · <a href="/issues?state={e(state)}&claimed=1">claimed</a>'
    return page("Issues", f"<p>{links}</p>" + err + table(["#", "Title", "State", "Milestone", "Labels", "Runner"], out))


def next_page(q: dict) -> str:
    try:
        got = core.next_issues(10)
    except Exception as err:  # noqa: BLE001
        return page("What needs work next", f'<p class="bad">GitHub unavailable: {e(str(err)[:200])}</p>')
    rows = [[f"#{i['number']}", e(i["title"])] for i in got["ready"]]
    return page("What needs work next", f"<p>Milestone: <b>{e(got['milestone'] or '—')}</b> (the pointed one, else the first open with a ready issue).</p>" +
                (table(["#", "Title"], rows) if rows else "<p class=muted>Nothing is ready: see the queue for write-ups and triage.</p>"))


def items_page(q: dict) -> str:
    c, s = core.cfg(), core.state()
    w = c["workers"]
    turns_max, tokens_max = w.get("issue_turns_max", 10), w.get("issue_tokens_max", 150000)
    spent, cap = core.spend_today(), core.daily_cap()
    rows = []
    for k, it in sorted(s["items"].items(), key=lambda kv: kv[1]["history"][0] if kv[1]["history"] else ""):
        u = it.get("usage") or {}
        prompt = u.get("fresh", 0) + u.get("cache_read", 0) + u.get("cache_write", 0)
        over = u.get("turns", 0) > turns_max or u.get("tokens", 0) > tokens_max
        checks = " ".join(f'<span class="{"ok" if r["ok"] else "bad"}">{"✓" if r["ok"] else "✗"} {e(r["name"])}</span>' for r in it["checks"])
        verdicts = e(", ".join(f"{v['verdict']} by {v['by']}" for v in it["verdicts"]) or "—")
        rows.append([f"<b>{e(k)}</b> {e(it['title'])}", e(it["state"]), checks or "—", verdicts, str(u.get("turns", "—")), f"{u.get('tokens', 0):,}",
                     f"{round(100 * u.get('cache_read', 0) / prompt)}%" if prompt else "—", f"${u.get('usd', it['cost_usd']):.2f}",
                     '<span class="bad">over budget</span>' if over else ""])
    head = (f"<p>Today ${spent:.2f} of the ${cap:.2f} daily cap {bar(spent, cap)}</p>"
            f"<p class=muted>Per issue from its done lines; flagged past {turns_max} turns or {tokens_max:,} tokens.</p>")
    return page("Items and cost", head + table(["Item", "State", "Checks", "Reviews", "Turns", "Tokens", "Cache hit", "Dollars", ""], rows))


PAGES = {"/specs": specs_page, "/milestones": milestones_page, "/issues": issues_page, "/next": next_page, "/items": items_page}
