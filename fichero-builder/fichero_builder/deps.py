"""`builder deps` (local.deps.weekly, owner-approved 2026-11-25): the open Dependabot pull requests against the land branch, read
with the manager's gh. A grouped minor/patch bump or a GitHub Actions bump whose required checks are all green is squash-merged
(one `deps` row); a major-version bump or one with a red required check is never merged: it becomes a builder step on the deps
lane, its brief built from the pull request. Anything else (checks still running, an ungrouped minor bump) waits, one row.
A pull request against any other base is left alone, and a land branch named `main` refuses the whole run. Config:
harness.toml [deps]; absent or `enabled = false` leaves the loop's job off (the verb still runs by hand)."""
from __future__ import annotations

import json
import re
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from fichero_builder import journal

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
BUMP = re.compile(r"(?:Bumps?|Updates?) \[?`?([\w@./-]+?)`?\]?(?:\([^)]*\))? from `?v?(\d(?:[\w.+-]*\w)?)`? to `?v?(\d(?:[\w.+-]*\w)?)`?")
NOTES = re.compile(r"https://github\.com/[^\s)>\]]+/releases[^\s)>\]]*")
RED, GREEN = ("fail", "cancel"), ("pass", "skipping")


@dataclass(frozen=True)
class Cfg:
    enabled: bool = False   # the loop's weekly job; off keeps today's behaviour
    day: str = "mon"        # after Dependabot's Monday run
    hour: int = 9           # local time, at or after
    lane: str = "deps"      # the lane a major or red bump is queued on
    worktree: str = ""      # that lane's tree ('' = <workroot>/wt-<lane>, the queue's managed tree)
    branch: str = ""        # the land branch ([land].branch)


def load(root) -> Cfg:
    f = Path(root) / "harness.toml"
    rules = tomllib.loads(f.read_text()) if f.is_file() else {}
    d = rules.get("deps", {})
    day = str(d.get("day", "mon"))[:3].lower()
    if day not in DAYS:
        raise ValueError(f"harness.toml [deps].day = {d.get('day')!r}: one of {', '.join(DAYS)}")
    tree = d.get("worktree") or (f"{rules['jail']['workroot']}/wt-{d.get('lane', 'deps')}" if rules.get("jail", {}).get("workroot") else "")
    return Cfg(bool(d.get("enabled", False)), day, int(d.get("hour", 9)), str(d.get("lane", "deps")), str(tree),
               str(rules.get("land", {}).get("branch", "")))


def due(cfg: Cfg, now: float, last: str) -> bool:
    """The weekly job runs once on [deps].day at or after [deps].hour; `last` is the date it last ran."""
    t = time.localtime(now)
    return cfg.enabled and DAYS[t.tm_wday] == cfg.day and t.tm_hour >= cfg.hour and last != time.strftime("%Y-%m-%d", t)


def bumps(pr: dict) -> list[tuple[str, str, str]]:
    """(package, from, to) for each update the title and body name, once each."""
    return list(dict.fromkeys(BUMP.findall(f"{pr.get('title', '')}\n{pr.get('body', '')}")))


def is_major(frm: str, to: str) -> bool:
    # ponytail: the leading number only; a 0.x minor bump counts as minor though semver calls it breaking
    a, b = (re.match(r"\d+", v) for v in (frm, to))
    return bool(a and b and a.group() != b.group())


def decide(pr: dict, checks: list[dict], branch: str) -> tuple[str, str]:
    """(action, why): merge, queue, wait or skip."""
    if pr.get("baseRefName") != branch:
        return "skip", f"base {pr.get('baseRefName')!r} is not {branch!r}"
    found = bumps(pr)
    actions = str(pr.get("headRefName", "")).startswith("dependabot/github_actions/")
    # an Actions bump is a tag move (v4 -> v5) whose green required checks ran the new action itself: its major merges too
    major = [] if actions else [f"{p} {a} -> {b}" for p, a, b in found if is_major(a, b)]
    red = [c["name"] for c in checks if c.get("bucket") in RED]
    if major or red:
        return "queue", "; ".join(x for x in (f"major: {', '.join(major)}" if major else "", f"red: {', '.join(red)}" if red else "") if x)
    if not checks or any(c.get("bucket") not in GREEN for c in checks):
        return "wait", "required checks not all green yet" if checks else "no required check reported"
    grouped = " group " in f" {pr.get('title', '').lower()} "
    if actions or grouped:
        return "merge", ("GitHub Actions bump" if actions else "grouped minor/patch bump") + ", required checks green"
    return "wait", "an ungrouped minor/patch bump: left for Dependabot's group or a person"


def brief(pr: dict, checks: list[dict], why: str, branch: str) -> str:
    rows = "\n".join(f"- {p}: {a} -> {b}" + (" (MAJOR)" if is_major(a, b) else "") for p, a, b in bumps(pr)) or "- (the PR names none: read it)"
    notes = "\n".join(f"- {u}" for u in dict.fromkeys(NOTES.findall(pr.get("body", "")))) or f"- {pr.get('url', '')}"
    red = [c["name"] for c in checks if c.get("bucket") in RED]
    return (f"Dependabot pull request #{pr['number']} ({pr.get('url', '')}): {pr.get('title', '')}\n"
            f"Why it was not merged: {why}.\n\nUpdates:\n{rows}\n\nRelease notes:\n{notes}\n\n"
            + (f"Failing required checks: {', '.join(red)}\n\n" if red else "")
            + f"Do: on your own branch from origin/{branch}, make the same update (the lock file and the manifest the PR changes), fix "
            "what the new version breaks (read the release notes for removed or renamed APIs), and run the tests of what you "
            "touched. Do not merge or comment on the pull request; the manager closes it once your step lands.\n")


def _gh(gh: str, args: list[str], cwd, run) -> subprocess.CompletedProcess:
    return run([gh, *args], cwd=str(cwd), capture_output=True, text=True)


def main_run(root, *, gh: str = "gh", dry: bool = False, out=print, run=subprocess.run, enqueue=None) -> int:
    """One pass. `enqueue(lane, worktree, step, brief_path)` queues a step (default queue.add); dry prints and changes nothing."""
    cfg = load(root)
    if not cfg.branch or cfg.branch == "main":
        out(f"builder deps refuses: the land branch is {cfg.branch or 'unset'!r}; it never works on main")
        return 1
    r = _gh(gh, ["pr", "list", "--author", "app/dependabot", "--base", cfg.branch, "--state", "open", "--limit", "100",
                 "--json", "number,title,body,url,headRefName,baseRefName"], root, run)
    if r.returncode:
        out(f"builder deps: gh pr list failed: {r.stderr.strip()[-300:]}")
        return 1
    if enqueue is None:
        from fichero_builder import queue

        def enqueue(lane, tree, step, path):
            queue.add(lane, tree, step, path, [])
    briefs = journal.STATE / "deps-briefs"
    for pr in json.loads(r.stdout or "[]"):
        c = _gh(gh, ["pr", "checks", str(pr["number"]), "--required", "--json", "name,bucket"], root, run)
        checks = json.loads(c.stdout or "[]") if c.stdout.strip().startswith("[") else []
        action, why = decide(pr, checks, cfg.branch)
        line = f"#{pr['number']} {pr.get('title', '')[:90]}: {action} ({why})"
        if dry:
            out(f"would {line}")
            continue
        detail = why
        if action == "merge":
            m = _gh(gh, ["pr", "merge", str(pr["number"]), "--squash"], root, run)
            action, detail = ("merged", why) if m.returncode == 0 else ("merge-failed", m.stderr.strip()[-300:])
        elif action == "queue":
            briefs.mkdir(parents=True, exist_ok=True)
            path = briefs / f"dep-{pr['number']}.txt"
            path.write_text(brief(pr, checks, why, cfg.branch))
            enqueue(cfg.lane, cfg.worktree, f"dep-{pr['number']}", str(path))
            action = "queued"
        journal.append("deps", pr=pr["number"], title=pr.get("title", "")[:200], url=pr.get("url", ""), state=action, detail=detail[:300])
        out(f"{action}: {line}")
    return 0


def main(a) -> int:
    return main_run(a.root, gh=a.gh, dry=a.dry_run)
