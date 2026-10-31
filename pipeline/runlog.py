"""The running log of the open-model trial (studio-harness-report § Running log): one TSV row per item and role, rebuilt
from the journal and Pi's session files, never typed by hand. `python -m pipeline run-log` rewrites the file; same
journal in, same file out. A batch task of several items shows the task's session totals on each of its items."""
from __future__ import annotations

import json
from pathlib import Path

from pipeline import ROOT, checks, coder, core, journal

LOG = ROOT / "agent-work" / "status" / "briefs" / "studio-run-log.tsv"
COLUMNS = ("date item stage role model provider precision ctx_cap prompt_tokens cached_tokens output_tokens tool_calls "
           "tool_errors diff_lines wall_min cost_usd pi_cost_usd ladder binding_verdict shadow_verdict rework_rounds "
           "false_done notes").split()


def price(cfg: dict, provider: str, model: str) -> dict:
    """The model's per-million prices as declared to Pi (models.json), {} when undeclared."""
    cat = json.loads((ROOT / cfg["workers"]["agent_dir"] / "models.json").read_text()).get("providers", {})
    return next((m for m in cat.get(provider, {}).get("models", []) if m["id"] == model), {})


def usd(st: dict, p: dict) -> float:
    """What the tokens cost at the declared prices (the provider's rates, not Pi's own arithmetic)."""
    c = p.get("cost") or {}
    return (st["fresh"] * c.get("input", 0) + st["cache_read"] * c.get("cacheRead", 0) + st["cache_write"] * c.get("cacheWrite", 0)
            + st["output"] * c.get("output", 0)) / 1e6


def sessions(events: list[dict], task: str, role: str) -> list[dict]:
    return [e for e in events if e["event"] == "worker" and e.get("task") == task and e.get("role") == role]


def totals(workers: list[dict]) -> dict | None:
    """Sum the session files of these worker windows: tokens, calls, errors, dollars. None when there were none."""
    if not workers:
        return None
    sts = [coder.status(Path(w["session_dir"])) for w in workers]
    n = {k: sum(s[k] for s in sts) for k in ("fresh", "cache_read", "cache_write", "output", "tool_errors", "cost_usd", "turns")}
    n["tool_calls"] = sum(sum(s["tool_calls"].values()) for s in sts)
    provider, _, model = workers[-1]["model"].partition("/")
    n["provider"], n["model"] = provider, model
    return n


def diff_lines(cfg: dict, it: dict, wt: str) -> str:
    try:
        out = checks.git(wt, "diff", "--numstat", f"{cfg['repo']['base']}...{it['sha']}")
        return str(sum(int(x) for row in out.splitlines() for x in row.split("\t")[:2] if x.isdigit()))
    except (RuntimeError, OSError, KeyError):
        return ""


def rows(cfg: dict | None = None, diff=diff_lines) -> list[dict]:
    cfg = cfg or core.cfg()
    events, st = journal.read(), core.state()
    stage = str(cfg.get("studio", {}).get("stage", ""))
    out = []
    for key, it in st["items"].items():
        task, wt = it["task"], st["tasks"][it["task"]]["worktree"]
        evs = [e for e in events if (e.get("key") or str(e.get("issue"))) == key]
        ladder = "green" if it["check_ok"] else (("red:" + next((r["name"] for r in it["checks"] if not r["ok"]), "?")) if it["checks"] else "")
        checked = [e for e in evs if e["event"] == "check"]
        bind = [v for v in it["verdicts"] if v["by"] == "reviewer"]
        shadow = [v for v in it["verdicts"] if v["by"] != "reviewer"]
        dones = [e["ts"] for e in evs if e["event"] == "issue_done"]
        wall = round((_t(dones[-1]) - _t(evs[0]["ts"])) / 60, 1) if dones else ""
        base = {"date": evs[0]["ts"][:10] if evs else "", "item": key, "stage": stage}
        for role in ("coder", "reviewer"):
            n = totals(sessions(events, task, role))
            if not n:
                continue
            p = price(cfg, n["provider"], n["model"])
            row = dict(base, role=role, model=n["model"], provider=n["provider"], precision=cfg.get("precision", {}).get(n["model"], ""),
                       ctx_cap=coder.context_cap(cfg, n["provider"]), prompt_tokens=n["fresh"] + n["cache_read"] + n["cache_write"],
                       cached_tokens=n["cache_read"], output_tokens=n["output"], tool_calls=n["tool_calls"], tool_errors=n["tool_errors"],
                       cost_usd=round(usd(n, p), 4), pi_cost_usd=round(n["cost_usd"], 4))
            if role == "coder":
                row.update(diff_lines=diff(cfg, it, wt), wall_min=wall, ladder=ladder, rework_rounds=it["attempts"],
                           false_done=int(bool(checked) and not checked[0]["ok"]),
                           notes=f"{it['state']}; task of {len(st['tasks'][task]['issues'])} item(s)")
            else:
                row.update(binding_verdict=bind[-1]["verdict"] if bind else "", shadow_verdict=shadow[-1]["verdict"] if shadow else "")
            out.append({c: row.get(c, "") for c in COLUMNS})
    return out


def _t(ts: str) -> float:
    import time
    return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S"))


def write(path: Path | None = None) -> dict:
    """Rewrite the log from the journal; returns {path, rows}."""
    path = Path(path or LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    rs = rows()
    path.write_text("\n".join(["\t".join(COLUMNS), *("\t".join(str(r[c]).replace("\t", " ").replace("\n", " ") for c in COLUMNS) for r in rs)]) + "\n")
    return {"path": str(path), "rows": len(rs)}


core.API["run_log"] = write
