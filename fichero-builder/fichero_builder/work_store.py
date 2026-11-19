"""builder-console.work-store.host-agnostic: milestones, issues, comments and labels through one interface, `WorkStore`.
Only the GitHub implementation exists; no verb calls it yet (`console.py`, `milestone.py` and `landed.py` still run `gh`)."""
from __future__ import annotations

import json
import re
import subprocess
from typing import Callable, Protocol, runtime_checkable


class StoreError(RuntimeError):
    pass


@runtime_checkable
class WorkStore(Protocol):
    def milestones(self) -> list[dict]: ...
    def issues(self, milestone: str) -> list[dict]: ...
    def milestone_of(self, issue: int) -> str: ...
    def comment(self, issue: int, text: str) -> None: ...
    def label(self, issue: int, add: list[str] = ..., remove: list[str] = ...) -> None: ...
    def close(self, issue: int, residue: str) -> None: ...
    def create(self, milestone: str, title: str, body: str, labels: list[str]) -> int: ...


def _gh(gh: str = "gh", cwd=None) -> Callable[..., str]:
    def run(*args: str) -> str:
        try:
            r = subprocess.run([gh, *args], capture_output=True, text=True, timeout=120, cwd=cwd)
        except (subprocess.TimeoutExpired, OSError) as e:
            raise StoreError(f"gh {' '.join(args[:2])}: {e}") from None
        if r.returncode:
            raise StoreError(f"gh {' '.join(args[:2])}: {r.stderr.strip()[-300:]}")
        return r.stdout
    return run


class GithubStore:
    def __init__(self, run: Callable[..., str] | None = None, gh: str = "gh", cwd=None):
        self.run = run or _gh(gh, cwd)

    def milestones(self) -> list[dict]:
        rows = json.loads(self.run("api", "repos/{owner}/{repo}/milestones", "--paginate", "-f", "state=all") or "[]")
        return [{"title": r["title"], "open": r["open_issues"], "closed": r["closed_issues"]} for r in rows]

    def issues(self, milestone: str) -> list[dict]:
        rows = json.loads(self.run("issue", "list", "--milestone", milestone, "--state", "open", "--limit", "200",
                                   "--json", "number,title,body,labels") or "[]")
        return [{**r, "labels": [x["name"] for x in r["labels"]]} for r in rows]

    def milestone_of(self, issue: int) -> str:
        """The title of the issue's milestone, '' when it has none."""
        return (json.loads(self.run("issue", "view", str(issue), "--json", "milestone") or "{}").get("milestone") or {}).get("title", "")

    def comment(self, issue: int, text: str) -> None:
        self.run("issue", "comment", str(issue), "--body", text)

    def label(self, issue: int, add: list[str] = (), remove: list[str] = ()) -> None:
        args = ["issue", "edit", str(issue)]
        for flag, names in (("--add-label", add), ("--remove-label", remove)):
            for n in names:
                args += [flag, n]
        self.run(*args)

    def close(self, issue: int, residue: str) -> None:
        self.run("issue", "close", str(issue), "--comment", residue)

    def create(self, milestone: str, title: str, body: str, labels: list[str]) -> int:
        args = ["issue", "create", "--milestone", milestone, "--title", title, "--body", body]
        for n in labels:
            args += ["--label", n]
        m = re.search(r"/issues/(\d+)", self.run(*args))
        if not m:
            raise StoreError("gh issue create printed no issue url")
        return int(m.group(1))


def open_store(name: str, **kw) -> WorkStore:
    """`[project].work_store`: `github` is built; the private-GitHub and in-Fichero stores are not."""
    if name == "github":
        return GithubStore(**kw)
    raise StoreError(f"work store {name!r} is not built (only 'github')")
