"""Model-free localisation (pipeline.batch-session, Agentless-style): from an issue's text and its spec lines, the
files, symbols and tests its brief names, and the issue's size, which picks the big or the small tier. `git grep`
finds the definitions (ponytail: the runner has no MCP client, so jcodemunch is the worker's tool, not the runner's;
add one if grep misses often, the `localised` journal lines show how often)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.+-]+\.(?:py|swift|md|sh|toml|json|ts|yml|yaml))(?:::(\w+))?")
# `name()`, `Type.name`, `snake_name`, `CamelName`: code-looking words in backticks (a behaviour id has a hyphen or
# is all lower-case dotted, so it does not look like this)
SYMBOL = re.compile(r"`(?:[A-Za-z_]\w*\.)*([A-Za-z_]\w*)(?:\(\))?`")
TEST_FILE = re.compile(r"(^|/)(test_[\w-]+\.py|[\w-]+_test\.py|[\w-]+Tests?\.swift)$")
# POSIX ERE (git grep -E): no \s, \b or (?:
DEF = ("^[[:space:]]*((public|private|internal|final|static|async|override) )*"
       "(def|class|func|struct|enum|protocol|actor)[[:space:]]+{}([^[:alnum:]_]|$)")
SMALL = {"files": 2, "symbols": 3, "tests": 1}  # ponytail: a guess; the page's per-issue cost tells if it is right


def _grep(repo: str, name: str, paths: list[str]) -> list[str]:
    # repo-wide: code only, not docs or test helpers
    paths = paths or [":(exclude,glob)**/*.md", ":(exclude,glob)**/conftest.py", ":(exclude,glob)**/test_*.py"]
    r = subprocess.run(["git", "-C", repo, "grep", "-n", "-E", DEF.format(re.escape(name)), "--", *paths],
                       capture_output=True, text=True)
    return [line.strip()[:200] for line in r.stdout.splitlines()[:3]]


def symbolish(word: str) -> bool:
    return len(word) > 3 and ("_" in word or word[0].isupper() and any(c.islower() for c in word[1:]))


def localise(repo: str, text: str) -> dict:
    """{files, tests: [{path, name, exists}], symbols: {name: [path:line: def ...]}, size: small|big|unknown}."""
    files, tests = [], []
    for path, name in dict.fromkeys(PATH.findall(text)):
        exists = (Path(repo) / path).exists()
        if TEST_FILE.search(path):
            body = (Path(repo) / path).read_text(errors="replace") if exists else ""
            tests.append({"path": path, "name": name, "exists": exists and (not name or f"def {name}(" in body)})
        elif exists and path not in files:
            files.append(path)
    # inside files the issue names, any backticked identifier is cheap and precise to look up; repo-wide only code-shaped ones
    names = [w for w in dict.fromkeys(SYMBOL.findall(text)) if len(w) > 3 and (files or symbolish(w))]
    symbols = {}
    for w in names[:12]:
        hits = (files and _grep(repo, w, files)) or _grep(repo, w, [])
        if hits:
            symbols[w] = hits
    touched = set(files) | {h.split(":", 1)[0] for hs in symbols.values() for h in hs}
    if not touched and not tests:
        size = "unknown"
    elif len(touched) <= SMALL["files"] and len(symbols) <= SMALL["symbols"] and len(tests) <= SMALL["tests"]:
        size = "small"
    else:
        size = "big"
    return {"files": sorted(touched), "tests": tests, "symbols": symbols, "size": size}


def section(loc: dict) -> list[str]:
    """The brief's "Where" and "The test to write first" sections."""
    out = []
    if loc["files"] or loc["symbols"]:
        out += ["## Where (found by the runner; edit these, do not search further)", *[f"- {f}" for f in loc["files"]]]
        out += [f"- `{name}`: {hit}" for name, hits in loc["symbols"].items() for hit in hits]
        out.append("")
    todo = [t for t in loc["tests"] if not t["exists"]]
    if todo:
        out += ["## The test to write first (it must fail before your change)",
                *[f"- {t['path']}" + (f"::{t['name']}" if t["name"] else "") for t in todo], ""]
    elif loc["tests"]:
        out += ["## Tests that name this behaviour (extend them; a new case must fail first)",
                *[f"- {t['path']}" + (f"::{t['name']}" if t["name"] else "") for t in loc["tests"]], ""]
    return out
