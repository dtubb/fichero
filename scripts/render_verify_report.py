#!/usr/bin/env python3
"""Render build/verify_all_report.json into a scannable HTML dashboard.

`verify_all.sh` writes a JSON report of failing checks. That JSON is precise
but not something you *read* — so failures stay invisible until someone greps
the log. This renders it into build/verify_all_report.html: one page, grouped
by failure kind, each check a row you can expand to see the output tail.

Usage:
    python3 scripts/render_verify_report.py \
        [build/verify_all_report.json] [build/verify_all_report.html]

Exit status mirrors the report: 0 if no failures, 1 if any — so it can gate a
release ("render + open the board, and don't ship while it's red").
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Failure kind -> (human label, severity). Severity drives the color stripe.
# guardrail/test/contract are "must-fix"; lint/other are "should-fix".
_KIND = {
    "build": ("Build", "critical"),
    "test": ("Tests", "critical"),
    "contract": ("API Contracts", "critical"),
    "guardrail": ("Architecture Guardrails", "warning"),
    "swift-lint": ("Swift Lint", "warning"),
    "python-lint": ("Python Lint", "warning"),
    "other": ("Other", "warning"),
}
_KIND_ORDER = ["build", "test", "contract", "guardrail", "swift-lint", "python-lint", "other"]


def _kind(cat: str) -> str:
    return cat if cat in _KIND else "other"


def render(report: dict, generated: str) -> str:
    checks = report.get("checks", [])
    failed = int(report.get("failed", len(checks)))
    tier = str(report.get("tier", "unknown"))

    groups: dict[str, list[dict]] = {}
    for c in checks:
        groups.setdefault(_kind(str(c.get("category", "other"))), []).append(c)

    # --- summary chips: one per kind that has failures, ordered by severity ---
    chips = []
    for k in _KIND_ORDER:
        n = len(groups.get(k, []))
        if not n:
            continue
        label, sev = _KIND[k]
        chips.append(
            f'<a class="chip {sev}" href="#g-{k}">'
            f'<span class="chip-n">{n}</span>{html.escape(label)}</a>'
        )
    chips_html = "".join(chips) or '<span class="chip ok"><span class="chip-n">0</span>All clear</span>'

    # --- grouped sections ---
    sections = []
    for k in _KIND_ORDER:
        items = groups.get(k)
        if not items:
            continue
        label, sev = _KIND[k]
        rows = []
        for c in items:
            lbl = html.escape(str(c.get("label", "(unnamed)")))
            cmd = html.escape(str(c.get("command", "")))
            tail = html.escape(str(c.get("output_tail", "")).rstrip())
            ft = c.get("failing_tests") or []
            ft_html = ""
            if ft:
                lis = "".join(f"<li>{html.escape(str(t))}</li>" for t in ft)
                ft_html = f'<ul class="failing">{lis}</ul>'
            rows.append(
                f"""<details class="row {sev}">
  <summary><span class="dot"></span><span class="lbl">{lbl}</span>
    <code class="cmd">{cmd}</code></summary>
  {ft_html}
  <pre class="tail">{tail or "(no output captured)"}</pre>
</details>"""
            )
        sections.append(
            f"""<section id="g-{k}" class="group {sev}">
  <h2><span class="count">{len(items)}</span>{html.escape(label)}</h2>
  {''.join(rows)}
</section>"""
        )
    sections_html = "\n".join(sections) or (
        '<section class="group ok"><h2>No failures recorded</h2>'
        '<p class="empty">This tier ran clean. Ship it.</p></section>'
    )

    status = "critical" if failed else "ok"
    verdict = f"{failed} failing check{'' if failed == 1 else 's'}" if failed else "All checks passed"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>verify_all — {html.escape(tier)}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="top {status}">
  <div class="top-in">
    <div class="eyebrow">Fichero · verify_all · <span class="mono">{html.escape(tier)}</span> tier</div>
    <h1>{verdict}</h1>
    <div class="meta">Generated {html.escape(generated)}</div>
    <nav class="chips">{chips_html}</nav>
  </div>
</header>
<main>
{sections_html}
</main>
<footer>Rendered from <code>build/verify_all_report.json</code> · click a row to expand its output</footer>
</body>
</html>"""


_CSS = """
:root {
  --bg: #f4f5f7; --panel: #ffffff; --ink: #1b1f24; --ink-2: #5a6472;
  --line: #e2e5ea; --accent: #2f6f6a;
  --ok: #2e7d5b; --warn: #b7791f; --crit: #c0392b;
  --ok-bg: #e6f3ec; --warn-bg: #fbf1dd; --crit-bg: #fbe7e4;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171b; --panel: #1c2127; --ink: #e7ebf0; --ink-2: #9aa6b4;
    --line: #2a313a; --accent: #57b3ab;
    --ok: #57c08b; --warn: #e0ac52; --crit: #ef7568;
    --ok-bg: #16302433; --warn-bg: #3a2c1233; --crit-bg: #3a1d1933;
  }
}
:root[data-theme="light"] {
  --bg: #f4f5f7; --panel: #ffffff; --ink: #1b1f24; --ink-2: #5a6472;
  --line: #e2e5ea; --accent: #2f6f6a;
  --ok: #2e7d5b; --warn: #b7791f; --crit: #c0392b;
  --ok-bg: #e6f3ec; --warn-bg: #fbf1dd; --crit-bg: #fbe7e4;
}
:root[data-theme="dark"] {
  --bg: #14171b; --panel: #1c2127; --ink: #e7ebf0; --ink-2: #9aa6b4;
  --line: #2a313a; --accent: #57b3ab;
  --ok: #57c08b; --warn: #e0ac52; --crit: #ef7568;
  --ok-bg: #16302433; --warn-bg: #3a2c1233; --crit-bg: #3a1d1933;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans);
  line-height: 1.5; -webkit-font-smoothing: antialiased; }
.mono { font-family: var(--mono); }
.top { border-bottom: 1px solid var(--line); background: var(--panel); }
.top-in { max-width: 60rem; margin: 0 auto; padding: 2.4rem 1.5rem 1.6rem; }
.eyebrow { font-size: .78rem; letter-spacing: .08em; text-transform: uppercase;
  color: var(--ink-2); }
.top h1 { margin: .5rem 0 .2rem; font-size: clamp(1.6rem, 4vw, 2.3rem); font-weight: 650;
  letter-spacing: -.02em; text-wrap: balance; }
.top.critical h1 { color: var(--crit); }
.top.ok h1 { color: var(--ok); }
.meta { color: var(--ink-2); font-size: .85rem; font-variant-numeric: tabular-nums; }
.chips { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1.1rem; }
.chip { display: inline-flex; align-items: center; gap: .45rem; text-decoration: none;
  padding: .3rem .7rem .3rem .4rem; border-radius: 999px; font-size: .82rem; font-weight: 550;
  color: var(--ink); background: var(--panel); border: 1px solid var(--line); }
.chip:hover { border-color: var(--accent); }
.chip-n { display: inline-grid; place-items: center; min-width: 1.4rem; height: 1.4rem;
  border-radius: 999px; font-variant-numeric: tabular-nums; font-size: .8rem; color: #fff; }
.chip.critical .chip-n { background: var(--crit); }
.chip.warning .chip-n { background: var(--warn); }
.chip.ok .chip-n { background: var(--ok); }
main { max-width: 60rem; margin: 0 auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.5rem; }
.group { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
.group h2 { display: flex; align-items: center; gap: .6rem; margin: 0; padding: .9rem 1.1rem;
  font-size: 1rem; font-weight: 620; border-bottom: 1px solid var(--line); }
.group .count { display: inline-grid; place-items: center; min-width: 1.6rem; height: 1.6rem;
  border-radius: 6px; font-size: .82rem; font-variant-numeric: tabular-nums; color: #fff; }
.group.critical .count { background: var(--crit); }
.group.warning .count { background: var(--warn); }
.group.ok .count { background: var(--ok); }
.group.ok h2 { border-bottom: none; }
.empty { padding: 0 1.1rem 1rem; color: var(--ink-2); }
.row { border-bottom: 1px solid var(--line); }
.row:last-child { border-bottom: none; }
.row > summary { display: flex; align-items: center; gap: .6rem; padding: .7rem 1.1rem;
  cursor: pointer; list-style: none; }
.row > summary::-webkit-details-marker { display: none; }
.row > summary:hover { background: color-mix(in srgb, var(--accent) 6%, transparent); }
.dot { width: .55rem; height: .55rem; border-radius: 999px; flex: none; }
.row.critical .dot { background: var(--crit); }
.row.warning .dot { background: var(--warn); }
.lbl { font-weight: 550; }
.cmd { margin-left: auto; font-family: var(--mono); font-size: .74rem; color: var(--ink-2);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 45%; }
.failing { margin: 0; padding: .2rem 1.1rem .6rem 2.3rem; }
.failing li { font-family: var(--mono); font-size: .78rem; color: var(--crit); }
.tail { margin: 0 1.1rem 1rem; padding: .8rem 1rem; background: var(--bg);
  border: 1px solid var(--line); border-radius: 8px; overflow-x: auto;
  font-family: var(--mono); font-size: .76rem; line-height: 1.5; white-space: pre;
  color: var(--ink); }
footer { max-width: 60rem; margin: 0 auto; padding: 1rem 1.5rem 3rem; color: var(--ink-2);
  font-size: .8rem; }
footer code, .cmd, .tail { font-family: var(--mono); }
@media (prefers-reduced-motion: no-preference) { .row[open] .tail { animation: fade .18s ease; } }
@keyframes fade { from { opacity: 0; } to { opacity: 1; } }
"""


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else Path("build/verify_all_report.json")
    dst = Path(argv[2]) if len(argv) > 2 else Path("build/verify_all_report.html")
    if not src.exists():
        print(f"render_verify_report: no report at {src}", file=sys.stderr)
        return 2
    report = json.loads(src.read_text())
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(render(report, generated))
    failed = int(report.get("failed", len(report.get("checks", []))))
    print(f"render_verify_report: {dst}  ({failed} failing)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
