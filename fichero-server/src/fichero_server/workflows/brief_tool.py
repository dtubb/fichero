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

TRUSTED = {"OWNER", "COLLABORATOR"}
_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.+-]+\.(?:py|swift|md|sh|toml|json|ts|yml|yaml))(?:::(\w+))?")
_SYMBOL = re.compile(r"`(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)(?:\(\))?`")
_TEST = re.compile(r"(^|/)(test_[\w-]+\.py|[\w-]+_test\.py|[\w-]+Tests?\.swift)$")
# POSIX ERE (git grep -E): no \s, \b or (?:
_DEF = ("^[[:space:]]*((public|private|internal|final|static|async|override) )*"
        "(def|class|func|struct|enum|protocol|actor)[[:space:]]+{}([^[:alnum:]_]|$)")


def fetch_issue(number: int, *, repo: str = "", gh: str = "gh") -> dict:
    argv = [gh, "issue", "view", str(number), "--json", "number,title,body,author,authorAssociation,comments"]
    if repo:
        argv += ["--repo", repo]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(f"gh could not read issue {number}: {r.stderr.strip()}")
    return json.loads(r.stdout)


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
    out = [f"# Issue #{issue['number']}: {issue['title']}", ""]
    body_ok = issue.get("authorAssociation") in TRUSTED
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
