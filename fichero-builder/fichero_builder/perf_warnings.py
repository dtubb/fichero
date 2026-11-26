"""The ranked warnings list and its one-issue-per-kind filing (#6610 Step 6, perf-sweep.warnings.ranked-list-and-issues).

One list for the three sources: the Xcode ratchet's kinds (scripts/check_xcode_warning_ratchet.py's rows), SwiftLint's per-rule counts
(`check_swiftlint_warning_ratchet.py --json`) and ruff's per-rule counts. Rows are `{source, platform, kind, count, trend, example}`,
ranked by count, written to `perf/<run>/warnings.json` with a pointer `perf/warnings-latest.json`. Each kind is one issue,
`Build warnings - <source>: <kind> (<count>)`, with the dedupe key `warn:<source>:<platform>:<kind>` in its body; a kind that reaches zero
closes its issue with the run id. `gh` is a callable (`gh("issue", "list", ...) -> stdout`), so a test holds an in-memory one."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fichero_builder import client

LABEL = "Build warnings"
MILESTONE = "performance-sweep"
EXAMPLES = 20
MAX_NEW = 25  # one run files at most this many new kinds; the rest wait for the next run (the cap is a flood guard, not a filter)
PHASE_KIND = "script phase without outputs: "

_BLOCK = re.compile(r"^\t\t(\w+)(?: /\* (.*?) \*/)? = \{\n(.*?)^\t\t\};", re.S | re.M)


def phases_without_outputs(pbxproj: str) -> list[str]:
    """The names of every PBXShellScriptBuildPhase with no `outputPaths` entry and no `alwaysOutOfDate = 1`: it runs on every build."""
    out = []
    for m in _BLOCK.finditer(pbxproj):
        body = m.group(3)
        if "isa = PBXShellScriptBuildPhase;" not in body or re.search(r"alwaysOutOfDate = 1;", body):
            continue
        outputs = re.search(r"outputPaths = \((.*?)\);", body, re.S)
        if outputs and outputs.group(1).strip():
            continue
        name = re.search(r'name = (?:"([^"]*)"|(\S+?));', body)
        out.append((name.group(1) or name.group(2)) if name else (m.group(2) or m.group(1)))
    return out


def _row(source, platform, kind, count, example="", examples=None) -> dict:
    return {"source": source, "platform": platform, "kind": kind, "count": count, "trend": None, "example": example,
            "examples": (examples or ([example] if example else []))[:EXAMPLES]}


def build_rows(*, xcode: dict | None = None, swiftlint: dict | None = None, ruff: dict | None = None, pbxproj: str | None = None) -> list[dict]:
    """`xcode` = {platform: [warning rows from the reader]}, `swiftlint` = the ratchet's `--json` document, `ruff` = {rule: count}."""
    rows: list[dict] = []
    for platform, warnings in (xcode or {}).items():
        by_kind: dict[str, list[dict]] = {}
        for w in warnings:
            by_kind.setdefault(w["kind"], []).append(w)
        for kind, ws in by_kind.items():
            at = [f"{w['file']}:{w['line']}" for w in ws]
            rows.append(_row("xcode", platform, kind, len(ws), at[0], at))
    for name in phases_without_outputs(pbxproj or ""):
        kind = f"{PHASE_KIND}'{name}'"
        if not any(r["kind"] == kind for r in rows):
            rows.append(_row("xcode", "mac", kind, 1, "fichero/fichero.xcodeproj/project.pbxproj"))
    for r in (swiftlint or {}).get("rules", []):
        rows.append(_row("swiftlint", "-", r["rule"], int(r["count"])))
    for rule, count in (ruff or {}).items():
        rows.append(_row("ruff", "-", rule, int(count)))
    return rows


def rank(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (-r["count"], r["source"], r["platform"], r["kind"]))


def _key(r: dict) -> tuple:
    return (r["source"], r["platform"], r["kind"])


def _read(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def latest(state) -> dict:
    """The newest list (the console reads it); no list yet is `{run: None, rows: []}`, never a green."""
    ptr = _read(Path(state) / "perf" / "warnings-latest.json")
    data = _read(Path(ptr["warnings"])) if ptr and ptr.get("warnings") else None
    return data or {"run": None, "rows": []}


def write_list(state, run: str, rows: list[dict]) -> dict:
    """Rank, put each row's trend (count minus the run before's, `None` for a kind not seen then), write warnings.json and the pointer."""
    perf = Path(state) / "perf"
    before = {_key(r): r for r in latest(state)["rows"]}
    ranked = []
    for r in rank(rows):
        p = before.get(_key(r))
        ranked.append({**r, "trend": r["count"] - p["count"] if p else None})
    out = perf / run / "warnings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {"run": run, "rows": ranked}
    out.write_text(json.dumps(data, indent=1))
    (perf / "warnings-latest.json").write_text(json.dumps({"run": run, "warnings": str(out)}, indent=1))
    return data


def dedupe_key(source: str, platform: str, kind: str) -> str:
    return f"warn:{source}:{platform}:{kind}"


def _title(r: dict) -> str:
    return f"Build warnings - {r['source']}: {r['kind']} ({r['count']})"


_WAYS = {
    "xcode": "Fix the warning at each line below; the count per kind is held by `scripts/check_xcode_warning_ratchet.py` and may only fall "
             "(the baseline `scripts/xcode_warning_baseline.json` is lowered in the same batch).",
    "swiftlint": "Fix each violation of the rule; `scripts/check_swiftlint_warning_ratchet.py` holds the total and `swiftlint lint` names the lines.",
    "ruff": "Fix each violation of the rule; `ruff check --select <rule>` names the lines.",
}


def _body(r: dict, run: str) -> str:
    extra = ""
    if r["kind"].startswith(PHASE_KIND):
        extra = ("\nThe phase runs on every build because it declares no outputs: give it a declared output file, or `alwaysOutOfDate = 1` where it "
                 "must run. That also shortens every incremental build. (A project.pbxproj edit: the owner or the manager makes it.)\n")
    return (f"{dedupe_key(r['source'], r['platform'], r['kind'])}\n\n"
            f"{r['count']} warning(s) of this kind on {r['platform']}, found by run {run}.\n"
            f"\nExample lines (up to {EXAMPLES}):\n" + "".join(f"- {e}\n" for e in (r.get("examples") or [r["example"] or "(see the tool output)"])) + f"{extra}\n"
            f"How to clear it: {_WAYS.get(r['source'], '')}\n")


def file_issues(rows: list[dict], measured: set, run: str, gh) -> list[int]:
    """One issue per kind, found again by its key; a changed count retitles it; a kind gone to zero closes it with the run id. A source
    or platform not in `measured` was not read this run and closes nothing. Returns the new issue numbers (a repeat run returns none)."""
    have = json.loads(gh("issue", "list", "--label", LABEL, "--state", "all", "--json", "number,title,body,state", "--limit", "1000") or "[]")
    open_by_key = {}
    for i in have:
        m = re.match(r"(warn:\S+?:\S+?:.*)", (i.get("body") or "").strip().splitlines()[0] if (i.get("body") or "").strip() else "")
        if m and i.get("state", "OPEN").upper() == "OPEN":
            open_by_key[m.group(1)] = i
    live = set()
    new: list[int] = []
    labelled = False
    for r in rank(rows):
        key = dedupe_key(r["source"], r["platform"], r["kind"])
        live.add(key)
        issue = open_by_key.get(key)
        if issue:
            if issue["title"] != _title(r):
                gh("issue", "edit", str(issue["number"]), "--title", _title(r))
            continue
        if len(new) >= MAX_NEW:
            continue
        if not labelled:
            if LABEL not in {x["name"] for x in json.loads(gh("label", "list", "--json", "name", "--limit", "1000") or "[]")}:
                gh("label", "create", LABEL)
            labelled = True
        url = gh("issue", "create", "--milestone", MILESTONE, "--title", _title(r), "--body", _body(r, run), "--label", LABEL).strip()
        new.append(int(url.rstrip("/").rsplit("/", 1)[-1]))
    for key, issue in open_by_key.items():
        _, source, platform, _kind = key.split(":", 3)
        if key not in live and (source, platform) in measured:
            gh("issue", "close", str(issue["number"]), "--comment", f"This kind reached zero in run {run}.")
    return new


def _xcode_reader():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_xcode_warning_ratchet", client.scripts_dir() / "check_xcode_warning_ratchet.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(a) -> int:
    from datetime import datetime, timezone

    from fichero_builder import journal, steps
    run = a.run or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[\w.-]+", run):
        print("a run id is letters, digits, dots, dashes and underscores")
        return 2
    xcode, swiftlint, ruff, measured = {}, None, None, set()
    try:
        if a.xcode:
            reader = _xcode_reader()
            for spec in a.xcode:
                platform, _, path = spec.partition("=")
                xcode[platform] = reader.read_warnings(path, None, platform)
                measured.add(("xcode", platform))
        if a.swiftlint:
            swiftlint = json.loads(Path(a.swiftlint).read_text())
            measured.add(("swiftlint", "-"))
        if a.ruff:
            ruff = json.loads(Path(a.ruff).read_text())
            measured.add(("ruff", "-"))
        pbx = Path(a.pbxproj).read_text() if a.pbxproj else None
    except Exception as exc:  # a source that cannot be read is said, never a quiet empty list
        print(f"perf-warnings: BLIND: {exc}")
        return 2
    if not measured and pbx is None:
        print("perf-warnings: nothing to read (--xcode, --swiftlint, --ruff or --pbxproj)")
        return 2
    rows = build_rows(xcode=xcode, swiftlint=swiftlint, ruff=ruff, pbxproj=pbx)
    data = write_list(journal.STATE, run, rows)
    for r in data["rows"][:10]:
        print(f"{r['count']:5d}  {r['source']:9s} {r['platform']:5s} {r['kind']}")
    if a.file:
        made = file_issues(rows, measured, run, lambda *args: steps._gh(a.gh, *args))
        print(f"filed {len(made)} new issue(s)")
    return 0
