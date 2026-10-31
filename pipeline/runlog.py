"""The running log of the open-model trial (studio-harness-report § Running log): one TSV row per item and role, rebuilt
from the journal and Pi's session files, never typed by hand. `python -m pipeline run-log` rewrites the file; same
journal in, same file out. A lane of several items shares one session: tokens and dollars are each item's own share (the difference between its
done lines); output tokens, tool calls and tool errors are the session's, shown on each."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pipeline import ROOT, checks, coder, core, journal

BRIEFS = Path(os.environ.get("PIPELINE_LOGS") or ROOT / "agent-work" / "status" / "briefs")  # a pinned copy writes to its checkout
LOG = BRIEFS / "studio-run-log.tsv"
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
            if role == "coder" and it.get("usage") and len(st["tasks"][task]["issues"]) > 1:  # the item's own share of a shared lane session (output and tool counts stay the session's)
                u = it["usage"]
                n.update(fresh=u["fresh"], cache_read=u["cache_read"], cache_write=u["cache_write"], cost_usd=u["usd"])
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


HANDOFF_LOG = BRIEFS / "studio-handoff-log.tsv"
HANDOFF_COLUMNS = "task n tokens_at_handoff ctx_cap pct note_bytes builder_note issues_before issues_after redid lost".split()


def handoffs(events: list[dict] | None = None, wt_of=None) -> list[dict]:
    """One row per handoff. redid: an issue the note's predecessor had finished that the successor finished again;
    lost: a finished issue whose commit is no longer in the lane's worktree history."""
    events = events if events is not None else journal.read()
    st = core.state() if wt_of is None else None
    out, seen = [], {}
    for i, e in enumerate(events):
        if e["event"] != "handoff":
            continue
        task = e["task"]
        n = seen[task] = seen.get(task, 0) + 1
        before = [x for x in events[:i] if x["event"] == "issue_done" and x.get("task") == task]
        after = [x for x in events[i + 1:] if x["event"] == "issue_done" and x.get("task") == task]
        gone = {x["key"] for x in before}
        wt = (wt_of or (lambda t: st["tasks"][t]["worktree"]))(task)
        lost = [x["key"] for x in before if _lost(wt, x["sha"])]
        out.append(dict(task=task, n=n, tokens_at_handoff=e.get("context", ""), ctx_cap=e.get("cap", ""),
                        pct=round(100 * e.get("context", 0) / e["cap"]) if e.get("cap") else "", note_bytes=e.get("note_bytes", ""),
                        builder_note=int(bool(e.get("builder_note"))), issues_before=len(before), issues_after=len(after),
                        redid=",".join(x["key"] for x in after if x["key"] in gone), lost=",".join(lost)))
    return out


def _lost(wt: str, sha: str) -> bool:
    try:
        checks.git(wt, "merge-base", "--is-ancestor", sha, "HEAD")
        return False
    except RuntimeError:
        return True


def write_handoffs(path: Path | None = None, **kw) -> dict:
    path = Path(path or HANDOFF_LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    rs = handoffs(**kw)
    path.write_text("\n".join(["\t".join(HANDOFF_COLUMNS), *("\t".join(str(r[c]) for c in HANDOFF_COLUMNS) for r in rs)]) + "\n")
    return {"path": str(path), "rows": len(rs)}


CLUSTER_LOG = BRIEFS / "studio-cluster-log.tsv"
CLUSTER_COLUMNS = ("task issues prompt_tokens cached_tokens cache_hit output_tokens cost_usd prompt_per_issue cost_per_issue "
                   "solo_prompt_per_issue solo_cost_per_issue ratio_prompt ratio_cost").split()


def cluster_rows(rs: list[dict], task_of) -> list[dict]:
    """Per task (a lane = a cluster): what its issues cost together and each, against the average of the single-issue tasks
    (the old per-item way): the owner's question is whether a cluster in one session needs fewer tokens per issue. Prompt
    tokens and dollars are each item's own share, so the sum over a task is the task's; output counts the session's once per item."""
    by: dict[str, list[dict]] = {}
    for r in rs:
        if r["role"] == "coder":
            by.setdefault(task_of(r["item"]), []).append(r)
    out = []
    for task, items in by.items():
        n, prompt = len(items), sum(int(r["prompt_tokens"] or 0) for r in items)
        cached, usd_ = sum(int(r["cached_tokens"] or 0) for r in items), sum(float(r["cost_usd"] or 0) for r in items)
        out.append(dict(task=task, issues=n, prompt_tokens=prompt, cached_tokens=cached, cache_hit=round(cached / prompt, 3) if prompt else 0,
                        output_tokens=max(int(r["output_tokens"] or 0) for r in items), cost_usd=round(usd_, 4),
                        prompt_per_issue=round(prompt / n), cost_per_issue=round(usd_ / n, 4)))
    solo = [o for o in out if o["issues"] == 1]
    sp = round(sum(o["prompt_per_issue"] for o in solo) / len(solo)) if solo else ""
    sc = round(sum(o["cost_per_issue"] for o in solo) / len(solo), 4) if solo else ""
    for o in out:
        o.update(solo_prompt_per_issue=sp, solo_cost_per_issue=sc,
                 ratio_prompt=round(o["prompt_per_issue"] / sp, 3) if sp else "", ratio_cost=round(o["cost_per_issue"] / sc, 3) if sc else "")
    return out


def write_clusters(rs: list[dict], path: Path | None = None) -> dict:
    path = Path(path or CLUSTER_LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    cs = cluster_rows(rs, lambda key: core.state()["items"][key]["task"])
    path.write_text("\n".join(["\t".join(CLUSTER_COLUMNS), *("\t".join(str(c[k]) for k in CLUSTER_COLUMNS) for c in cs)]) + "\n")
    return {"path": str(path), "rows": len(cs)}


def write(path: Path | None = None) -> dict:
    """Rewrite the log from the journal; returns {path, rows}."""
    path = Path(path or LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    rs = rows()
    path.write_text("\n".join(["\t".join(COLUMNS), *("\t".join(str(r[c]).replace("\t", " ").replace("\n", " ") for c in COLUMNS) for r in rs)]) + "\n")
    return {"path": str(path), "rows": len(rs), "clusters": write_clusters(rs, path.with_name(CLUSTER_LOG.name))}


core.API["run_log"] = lambda: {**write(), "handoffs": write_handoffs()}
