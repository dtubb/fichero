"""`builder order --file F`: the owner's new build order (from the console) as one commit on branch `build-order`, queued as a
tiny batch the loop checks and lands like any other (dev-workflows.run.loop-status, Console; issues-and-labels build order).
F is JSON {"order": [milestone, ...], "parked": [milestone, ...]}: the whole `## In order` list top to bottom, and the
milestones the owner parked. A line keeps its text; a milestone new to the list gets a bare line. The order the loop uses is
the landed one, so a pending reorder shows as saving until its batch lands."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from fichero_builder import journal, queue

FILE = Path("docs/contributor_manual/specs/build-order.md")
LANE = "build-order"
LINE = re.compile(r"^\d+\.\s+`([^`]+)`(.*)$")


def rewrite(text: str, order: list[str], parked: list[str], today: str = "") -> str:
    """The file with `## In order` renumbered to `order` and each newly parked milestone added under `## Parked`; a
    milestone in `order` is taken out of any parked line. Refuses (ValueError) a name in both lists or listed twice."""
    if len(set(order)) != len(order) or set(order) & set(parked):
        raise ValueError("a milestone is listed twice, or both ordered and parked")
    head, rest = text.split("## In order", 1)
    body, _, tail = rest.partition("\n## ")
    tail = "## " + tail if tail else "## Parked\n"
    lines = {m.group(1): m.group(2) for m in map(LINE.match, body.splitlines()) if m}
    ordered = "\n".join(f"{i}. `{n}`{lines.get(n, '')}" for i, n in enumerate(order, 1))
    out = []
    for ln in tail.splitlines():
        if ln.startswith("- "):
            for n in order:  # unparked: out of its bucket line
                ln = re.sub(rf"`{re.escape(n)}`(,\s*)?", "", ln)
            if not re.search(r"`[^`]+`", ln):
                continue
        out.append(ln)
    already = set(re.findall(r"`([^`]+)`", "\n".join(out)))
    out += [f"- `{n}` — parked by the owner{(' ' + today) if today else ''}." for n in parked if n not in already]
    return f"{head}## In order\n\n{ordered}\n\n" + "\n".join(out).rstrip("\n") + "\n"


def _git(cwd, *a) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True)


def save(root, order: list[str], parked: list[str], branch: str = "integration") -> tuple[int, str]:
    """Commit the rewrite in the `build-order` worktree (beside the checkout; made from origin/<branch> when missing or
    when its last reorder has landed), then queue it on the external lane `build-order` and say DONE at the commit."""
    if pending():
        return 1, "a reorder is still saving: it lands first, then the next one"
    root = Path(root).resolve()
    wt = root.parent / LANE
    _git(root, "fetch", "-q", "origin", branch)
    if not wt.is_dir():
        r = _git(root, "worktree", "add", "-q", "-B", LANE, str(wt), f"origin/{branch}")
        if r.returncode:
            return 1, f"could not make the {LANE} worktree: {r.stderr.strip()[-300:]}"
    elif not _git(wt, "merge-base", "--is-ancestor", "HEAD", f"origin/{branch}").returncode:  # the last reorder landed: start fresh
        _git(wt, "checkout", "-q", "-B", LANE, f"origin/{branch}")
    f = wt / FILE
    try:
        new = rewrite(f.read_text(), order, parked, time.strftime("%Y-%m-%d"))
    except (OSError, ValueError) as e:
        return 1, str(e)
    if new == f.read_text():
        return 0, "the order is unchanged"
    f.write_text(new)
    moved = ", ".join(order[:3]) + (" …" if len(order) > 3 else "")
    msg = f"docs(build-order): owner reorders: {moved}" + (f"; parks {', '.join(parked)}" if parked else "") + "\n\nWritten-By: Claude\n"
    r = _git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-q", "-m", msg, "--", str(FILE))
    if r.returncode:
        return 1, f"commit failed: {r.stderr.strip()[-300:]}"
    sha = _git(wt, "rev-parse", "HEAD").stdout.strip()
    step = f"reorder-{time.strftime('%Y%m%d-%H%M%S')}"
    brief = journal.STATE / f"{step}.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(f"# The owner's build order\n\n{msg}")
    queue.add(LANE, str(wt), step, str(brief), [], kind="external")
    if why := queue.done(LANE, sha):
        return 1, why
    journal.append("order", sha=sha, step=step, order=order, parked=parked)
    return 0, f"saving: {sha[:9]} queued on lane {LANE} ({step})"


def pending() -> bool:
    """A reorder queued and not landed yet: the console shows it as saving."""
    return any(x["id"] == LANE and any(s["state"] != "landed" for s in x["steps"]) for x in queue.load())


def main(a) -> int:
    data = json.loads(Path(a.file).read_text())
    import tomllib
    branch = tomllib.loads((Path(a.root) / "harness.toml").read_text()).get("land", {}).get("branch", "integration")
    rc, out = save(a.root, [str(x) for x in data.get("order", [])], [str(x) for x in data.get("parked", [])], branch)
    print(out)
    return rc
