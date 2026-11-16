"""`builder file`: a milestone and one issue under it, from a brief (dev-workflows.tool.file).

Idempotent: the milestone is created only if absent, the issue is found again by its exact title in that milestone and
edited rather than filed twice. Every write is a `file` journal row; --dry writes nothing. Never pushes. Standard library and `gh` only."""
from __future__ import annotations

import json

from fichero_builder import journal, steps

API = "repos/{owner}/{repo}/milestones"


def run(*, milestone: str, title: str, body: str, labels: list[str], gh: str = "gh", dry_run: bool = False, say=print) -> int | None:
    """The issue number (None on a dry run that would create it). Raises steps.Refused when gh fails or an input is empty."""
    if not (milestone.strip() and title.strip() and body.strip()):
        raise steps.Refused("--milestone, --title and a non-empty body are all required")
    rows = json.loads(steps._gh(gh, "api", f"{API}?state=all&per_page=100", "--paginate") or "[]")
    have = any(m.get("title") == milestone for m in rows)
    if not have:
        journal.append("file", what="milestone-create", dry=dry_run, milestone=milestone)
        say(f"{'would create' if dry_run else 'created'} milestone: {milestone}")
        if not dry_run:
            steps._gh(gh, "api", "-X", "POST", API, "-f", f"title={milestone}")
    n = steps.find(gh, milestone, title) if have else None
    action = "update" if n else "create"
    journal.append("file", what=f"issue-{action}", dry=dry_run, milestone=milestone, title=title, labels=labels, issue=n)
    if dry_run:
        say(f"would {action}{' #' + str(n) if n else ''}: {title} [{','.join(labels)}] in {milestone}")
        say(f"--- body ---\n{body}")
        return n
    steps.ensure_labels(gh, labels)
    if n:
        steps._gh(gh, "issue", "edit", str(n), "--body", body, *(["--add-label", ",".join(labels)] if labels else []))
    else:
        url = steps._gh(gh, "issue", "create", "--milestone", milestone, "--title", title, "--body", body,
                        *(["--label", ",".join(labels)] if labels else [])).strip()
        n = int(url.rstrip("/").rsplit("/", 1)[-1])
    say(f"{action}d #{n}: {title}")
    return n
