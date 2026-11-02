"""The brief tool: an issue's body and trusted comments, plus where the code is, as the worker's brief (#6116).

(dev-workflows.builder.cluster; security.untrusted-text.) Plain module, no imports from the rest of the engine
(the Builder may become its own app). Localisation is ported from the frozen pipeline/localise.py: model-free,
`git grep` for the definitions of what the issue names.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}  # spec:197
_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.+-]+\.(?:py|swift|md|sh|toml|json|ts|yml|yaml))(?:::(\w+))?")
_SYMBOL = re.compile(r"`(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)(?:\(\))?`")
_TEST = re.compile(r"(^|/)(test_[\w-]+\.py|[\w-]+_test\.py|[\w-]+Tests?\.swift)$")
# POSIX ERE (git grep -E): no \s, \b or (?:
_DEF = ("^[[:space:]]*((public|private|internal|final|static|async|override) )*"
        "(def|class|func|struct|enum|protocol|actor)[[:space:]]+{}([^[:alnum:]_]|$)")


def _api(path: str, gh: str) -> object:
    r = subprocess.run([gh, "api", "--paginate", "--slurp", path], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(f"gh could not read {path}: {r.stderr.strip()}")
    data = json.loads(r.stdout)
    # --slurp wraps pages in a list; an issue (object) comes back as [obj]
    return [x for page in data for x in (page if isinstance(page, list) else [page])] if isinstance(data, list) else data


def fetch_issue(number: int, *, repo: str = "", gh: str = "gh") -> dict:
    """Issue + comments from the REST API (`gh issue view` has no authorAssociation), in the shape build() reads."""
    if not repo:
        r = subprocess.run([gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                           capture_output=True, text=True, timeout=60)
        repo = r.stdout.strip()
    iss = _api(f"repos/{repo}/issues/{number}", gh)
    iss = iss[0] if isinstance(iss, list) else iss
    comments = _api(f"repos/{repo}/issues/{number}/comments", gh)
    return {"number": iss["number"], "title": iss["title"], "body": iss.get("body"),
            "author": iss.get("user") or {}, "authorAssociation": iss.get("author_association"),
            "comments": [{"author": c.get("user") or {}, "authorAssociation": c.get("author_association"),
                          "body": c.get("body"), "createdAt": c.get("created_at", "")} for c in comments]}


def _grep(repo: str, name: str, paths: list[str]) -> list[str]:
    paths = paths or [":(exclude,glob)**/*.md", ":(exclude,glob)**/conftest.py", ":(exclude,glob)**/test_*.py"]
    r = subprocess.run(["git", "-C", repo, "grep", "-n", "-E", _DEF.format(re.escape(name)), "--", *paths],
                       capture_output=True, text=True)
    return [line.strip()[:200] for line in r.stdout.splitlines()[:3]]


def _symbolish(w: str) -> bool:
    return len(w) > 3 and ("_" in w or w[0].isupper() and any(c.islower() for c in w[1:]))


def localise(repo: str, text: str) -> dict:
    """{files, tests: [{path, name, exists}], symbols: {name: [path:line: def ...]}}."""
    files: list[str] = []
    tests = []
    for path, name in dict.fromkeys(_PATH.findall(text)):
        exists = (Path(repo) / path).exists()
        if _TEST.search(path):
            body = (Path(repo) / path).read_text(errors="replace") if exists else ""
            tests.append({"path": path, "name": name, "exists": exists and (not name or f"def {name}(" in body)})
        elif exists and path not in files:
            files.append(path)
    symbols = {}
    for w in [w for w in dict.fromkeys(_SYMBOL.findall(text)) if len(w) > 3 and (files or _symbolish(w))][:12]:
        hits = (files and _grep(repo, w, files)) or _grep(repo, w, [])
        if hits:
            symbols[w] = hits
    touched = set(files) | {h.split(":", 1)[0] for hs in symbols.values() for h in hs}
    return {"files": sorted(touched), "tests": tests, "symbols": symbols}


def build(issue: dict, *, repo: str) -> str:
    """The brief text. An untrusted body or comment never reaches it (named once, so the worker knows)."""
    body_ok = issue.get("authorAssociation") in TRUSTED
    title = issue["title"] if body_ok else "(title left out: its author is not trusted)"
    out = [f"# Issue #{issue['number']}: {title}", ""]
    out += [issue.get("body") or "", ""] if body_ok else ["(The issue body is left out: its author is not trusted.)", ""]
    comments = sorted(issue.get("comments") or [], key=lambda c: c.get("createdAt", ""), reverse=True)
    trusted = [c for c in comments if c.get("authorAssociation") in TRUSTED]
    if trusted:
        out += ["## Comments (newest first; owner and collaborators only)"]
        for c in trusted:
            out += [f"### {(c.get('author') or {}).get('login', '?')} {c.get('createdAt', '')}", c.get("body") or "", ""]
    if len(trusted) < len(comments):
        out += [f"({len(comments) - len(trusted)} comment(s) from untrusted authors left out.)", ""]
    loc = localise(repo, "\n".join([issue.get("body") or "" if body_ok else ""] + [c.get("body") or "" for c in trusted]))
    if loc["files"] or loc["symbols"]:
        out += ["## Where (found by the tool; edit these, do not search further)", *[f"- {f}" for f in loc["files"]]]
        out += [f"- `{n}`: {h}" for n, hs in loc["symbols"].items() for h in hs] + [""]
    todo = [t for t in loc["tests"] if not t["exists"]]
    if todo:
        out += ["## The test to write first (it must fail before your change)",
                *[f"- {t['path']}" + (f"::{t['name']}" if t["name"] else "") for t in todo], ""]
    elif loc["tests"]:
        out += ["## Tests that name this behaviour (extend them; a new case must fail first)",
                *[f"- {t['path']}" + (f"::{t['name']}" if t["name"] else "") for t in loc["tests"]], ""]
    return "\n".join(out)


def cluster(issues: list[dict], *, repo: str, branch: str, base: str, rules: str = "", where: list[str] = ()) -> str:
    """One brief for a cluster: two preamble lines, the project's [brief].rules from harness.toml as the THIRD line with
    `#N` filled from the cluster's issues (so no brief needs a hand edit), the rest of the preamble, then every issue's
    build(). The worker needs no issue tool: everything it may read is in the brief."""
    numbers = ", ".join(f"#{i['number']}" for i in issues)
    head = [f"You are a worker in the dev harness. Branch {branch} in this worktree (base {base}). No push.",
            "Everything you need is below: the issues' text, trusted comments and where the code is. There is no issue "
            "tool to call; do not try to read the issues again."]
    if rules.strip():
        head.append(" ".join(rules.strip().replace("#N", numbers).split("\n")))
    head += [f"This step owes {numbers}. Put `Fixes #N` on its own line on the commit that finishes issue N, and `Part of #N` on any commit before that: "
             "an issue closes only through that line when the step lands.",
             "One commit per issue. Test first, see it fail, then fix. Before changing a shared function, grep every "
             "reader and run their tests. If the behaviour is already in place, do not commit a test alone: commit the "
             "proving test with the line `Already built: #N <test path>::<test name>` in the message (that test passes on "
             "the base by design, so the check owes it no red; the landing comments the issue with the test).",
             "When all are committed print on its own line: DONE <short sha of branch head>, then the list of commits and "
             "which tests you ran.", ""]
    if where:
        head += ["## Where to start (found by the tool; your code tools find the rest)", *[f"- {w}" for w in where], ""]
    return "\n".join(head + [build(i, repo=repo) for i in issues])
