"""`builder steps`: an APPROVED spec's build order as issues under the spec's milestone (dev-workflows.tool.steps).

One issue per step, found again by its exact title ("<milestone> Step N.M: <title>") so a second run edits it rather than
filing another; every write is a journal row. A PROPOSED spec is refused. Standard library and `gh` only."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from fichero_builder import journal

_STEP = re.compile(r"^####\s+Step\s+(\d+\.\d+)\s+—\s+(.*?)(?:\s+\(#\d+\))?\s*$")
_STAGE = re.compile(r"^###\s+Stage\s+(\d+)\b")
_FIELD = re.compile(r"^-\s+(Behaviours|Tests|Depends on|Size):\s*(.*?)\s*$")


class Refused(Exception):
    pass


def parse(text: str) -> tuple[str, list[dict]]:
    """(milestone, steps in file order). Refuses a spec that is not APPROVED or names no milestone or has no steps."""
    head = text.splitlines()[:20]
    if not any("**Status: APPROVED" in line for line in head):
        raise Refused("the spec is not APPROVED (a `> **Status: APPROVED` line in its first 20 lines); a PROPOSED spec is not filed")
    m = next((re.match(r">\s*Milestone:\s*(\S+)", line) for line in head if line.startswith(">") and "Milestone:" in line), None)
    if not m:
        raise Refused("the spec has no `> Milestone: <name>` line")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^##\s+Build order\b", line)), None)
    if start is None:
        raise Refused("the spec has no `## Build order` section")
    steps: list[dict] = []
    stage, cur = "", None
    for line in lines[start + 1:]:
        if re.match(r"^##\s", line):
            break
        if s := _STAGE.match(line):
            stage = s.group(1)
        elif s := _STEP.match(line):
            cur = {"id": s.group(1), "title": s.group(2), "stage": stage or s.group(1).split(".")[0], "fields": {}}
            steps.append(cur)
        elif cur and (f := _FIELD.match(line)):
            cur["fields"][f.group(1)] = f.group(2)
    if not steps:
        raise Refused("the build order has no `#### Step N.M — title` headings")
    for i, s in enumerate(steps):
        dep = s["fields"].get("Depends on")
        if dep is None:  # the template's default: the step before, within the stage
            prev = steps[i - 1] if i and steps[i - 1]["stage"] == s["stage"] else None
            s["depends"] = [prev["id"]] if prev else []
        else:
            s["depends"] = [d.strip() for d in dep.split(",") if re.fullmatch(r"\d+\.\d+", d.strip())]
    return m.group(1), steps


def title_of(slug: str, step: dict) -> str:
    return f"{slug} Step {step['id']}: {step['title']}"


def body_of(step: dict, spec: str, numbers: dict[str, int]) -> str:
    f = step["fields"]
    out = [f"Step: {step['id']}", f"Spec: {spec}", "", f"Behaviours: {f.get('Behaviours', '')}", f"Tests: {f.get('Tests', '')}",
           f"Size: {f.get('Size', '')}"]
    if step["depends"]:
        out.append("Depends on: " + ", ".join(f"#{numbers[d]}" if d in numbers else f"step {d} (not filed yet)" for d in step["depends"]))
    return "\n".join(out) + "\n"


def _gh(gh: str, *args) -> str:
    try:
        r = subprocess.run([gh, *args], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise Refused(f"gh {' '.join(args[:2])} timed out after 120 s") from None
    if r.returncode:
        raise Refused(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[-300:]}")
    return r.stdout


def find(gh: str, slug: str, title: str) -> int | None:
    rows = json.loads(_gh(gh, "issue", "list", "--milestone", slug, "--state", "all",
                          "--json", "number,title", "--limit", "1000") or "[]")
    return next((r["number"] for r in rows if r["title"] == title), None)


def ensure_labels(gh: str, names: list[str]) -> list[str]:
    """`gh label create` for each name the repo lacks (one `gh label list` first; an existing label is never re-created).
    Returns the names created. Labels are the step key: `spec:<spec file stem>` and `step:N.M` (dev-workflows.tool.steps)."""
    have = {r["name"] for r in json.loads(_gh(gh, "label", "list", "--json", "name", "--limit", "1000") or "[]")}
    made = [n for n in names if n not in have]
    for n in made:
        _gh(gh, "label", "create", n)
    return made


def run(spec_path, *, gh: str = "gh", dry_run: bool = False, say=print) -> None:
    spec = Path(spec_path)
    slug, steps = parse(spec.read_text())
    numbers: dict[str, int] = {}
    spec_label = f"spec:{spec.stem}"
    if not dry_run:
        ensure_labels(gh, [spec_label, *(f"step:{s['id']}" for s in steps)])
    for s in steps:
        title = title_of(slug, s)
        n = find(gh, slug, title)
        body = body_of(s, spec.as_posix(), numbers)
        labels = f"{spec_label},step:{s['id']}"
        if dry_run:
            say(f"would {'update #' + str(n) if n else 'create'}: {title} [{labels}]")
            if n:
                numbers[s["id"]] = n
            continue
        if n:
            _gh(gh, "issue", "edit", str(n), "--body", body, "--add-label", labels)
            action = "update"
        else:
            url = _gh(gh, "issue", "create", "--milestone", slug, "--title", title, "--body", body, "--label", labels).strip()
            n = int(url.rstrip("/").rsplit("/", 1)[-1])
            action = "create"
        numbers[s["id"]] = n
        journal.append("steps", spec=spec.as_posix(), step=s["id"], action=action, issue=n, title=title)
        say(f"{action}d #{n}: {title}")
