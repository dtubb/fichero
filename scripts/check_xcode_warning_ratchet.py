#!/usr/bin/env python3
"""Xcode warning ratchet (#6610, perf-sweep.warnings.*): the count of each KIND of compiler, clang and build-system warning, per
platform, may only fall. Shaped like check_swiftlint_warning_ratchet.py.

The warnings are read from a result bundle (`-resultBundlePath`, read with `xcrun xcresulttool get build-results --path <x>`; a
`.json` file of that output is read as it is), never from the log alone. The kept build log is the fallback when there is no bundle.
Each warning is normalised to (platform, kind, file, line, message); a kind is the message with its quoted names and numbers
replaced by `_` (so two deprecations of different symbols are one kind), prefixed by its family (Sendable, concurrency, unused,
deprecated); for clang the `[-W...]` flag; for the build system the phase or target kept.

scripts/xcode_warning_baseline.json = {platform: {kind: count}}, held EXACTLY. Counts are per kind, not per file, so a warning that
moves file is not new. A kind that falls is lowered in the baseline in the same run; a raised baseline in a diff is refused
(`--check-baseline <new> --was <old>`).

  --platform P --bundle B [--log L]   measure and hold
  --update-baseline                   take the measured counts as the platform's baseline
  --since <base bundle or json>       only this item's new lines: kinds whose count rose over the base, naming the surplus lines

Exit codes: 0 held (or fell, or skipped: no bundle or log named, as in the guards rung), 1 GREW, 2 BLIND (a named bundle/log that is missing or unreadable, a missing default baseline).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "xcode_warning_baseline.json"
BLIND_EXIT_CODE = 2

COMPILER_LINE = re.compile(r"^(.+?):(\d+):(\d+): warning: (.*)$")
SYSTEM_LINE = re.compile(r"^warning: (.*)$")
QUOTED = re.compile(r"'[^']*'")
NUMBER = re.compile(r"\d+")
CLANG_FLAG = re.compile(r"\[(-W[\w+-]+)\]\s*$")
PHASE = re.compile(r"Run script build phase ('[^']*') will be run during every build because it does not specify any outputs", re.I)
# (family, pattern): the first match is the family the compiler's own wording gives
FAMILIES = (
    ("Sendable", re.compile(r"sendable", re.I)),
    ("concurrency", re.compile(r"actor|isolat|concurren|async", re.I)),
    ("deprecated", re.compile(r"deprecated", re.I)),
    ("unused", re.compile(r"never used|never mutated|unused|never read", re.I)),
)
SYSTEM_KINDS = (
    ("duplicate output file", re.compile(r"duplicate output file|multiple commands produce", re.I)),
    ("deployment target", re.compile(r"deployment target", re.I)),
    ("missing Info.plist key", re.compile(r"info\.plist", re.I)),
    ("linker", re.compile(r"\bld\b|linker|ld:", re.I)),
)


class Blind(Exception):
    """The warnings cannot be measured at all."""


def _squash(message: str) -> str:
    return NUMBER.sub("_", QUOTED.sub("_", message)).strip()


def normalise_kind(message: str, issue_type: str = "") -> str:
    """The kind of one warning message; `issue_type` is the bundle's (empty for a log line, where the shape tells)."""
    if (m := PHASE.search(message)):
        return f"script phase without outputs: {m.group(1)}"
    system = "build system" in issue_type.lower()
    if not system:
        if (m := CLANG_FLAG.search(message)):
            return m.group(1)
        for family, pat in FAMILIES:
            if pat.search(message):
                return "deprecated: _" if family == "deprecated" else f"{family}: {_squash(message)}"
        return _squash(message)
    for kind, pat in SYSTEM_KINDS:
        if pat.search(message):
            return kind
    return NUMBER.sub("_", message).strip()


# SwiftLint reports into the build as warnings ending "(rule_name)"; its own ratchet (check_swiftlint_warning_ratchet.py)
# holds them per rule, so this one skips them rather than counting each rule twice against a zero baseline.
SWIFTLINT_LINE = re.compile(r"Violation: .*\([a-z_]+\)\s*$")


def _row(platform, message, file, line, issue_type="") -> dict:
    return {"platform": platform, "kind": normalise_kind(message, issue_type), "file": file, "line": line, "message": message}


def _from_url(url: str) -> tuple[str, int]:
    path, _, frag = url.partition("#")
    if path.startswith("file://"):
        path = path[len("file://"):]
    m = re.search(r"StartingLineNumber=(\d+)", frag)
    return unquote(path).lstrip("/"), int(m.group(1)) if m else 0


def _load_results(path: Path) -> dict:
    """Build-results JSON: the file as it is, or the output of xcresulttool over a `.xcresult` folder."""
    try:
        if path.is_dir():
            out = subprocess.run(["xcrun", "xcresulttool", "get", "build-results", "--path", str(path)],
                                 capture_output=True, text=True, timeout=300, check=True).stdout
        else:
            out = path.read_text(encoding="utf-8")
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise Blind(f"could not read the result bundle {path}: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("warnings"), list):
        raise Blind(f"{path} has no `warnings` list: not a build-results document")
    return data


def read_bundle(path, platform: str) -> list[dict]:
    rows = []
    for w in _load_results(Path(path))["warnings"]:
        file, line = _from_url(w.get("sourceURL") or "")
        rows.append(_row(platform, w.get("message", ""), file or w.get("targetName", ""), line, w.get("issueType", "")))
    return rows


def read_log(path, platform: str) -> list[dict]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise Blind(f"could not read the build log {path}: {exc}") from None
    rows = []
    for ln in text.splitlines():
        if (m := COMPILER_LINE.match(ln)):
            rows.append(_row(platform, m.group(4), m.group(1).lstrip("/"), int(m.group(2))))
        elif (m := SYSTEM_LINE.match(ln)):
            rows.append(_row(platform, m.group(1), "", 0, "Build System Warning"))
    return rows


def read_warnings(bundle, log, platform: str) -> list[dict]:
    """The bundle when there is one; else the log; neither is BLIND, never an empty green."""
    if bundle and Path(bundle).exists():
        return [r for r in read_bundle(bundle, platform) if not SWIFTLINT_LINE.search(r["message"])]
    if log and Path(log).is_file():
        return [r for r in read_log(log, platform) if not SWIFTLINT_LINE.search(r["message"])]
    raise Blind("no result bundle and no build log to read")


def count_kinds(rows: list[dict]) -> dict:
    return dict(Counter(r["kind"] for r in rows))


def _load_baseline(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Blind(f"baseline unreadable at {path}: {exc}") from None
    except ValueError:
        raise Blind(f"{path} is not valid JSON: restore it from git rather than deleting it") from None
    if not isinstance(data, dict):
        raise Blind(f"{path} is not a {{platform: {{kind: count}}}} object")
    return data


def _write_baseline(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _at(r: dict) -> str:
    return f"{r['file']}:{r['line']}" if r["file"] else "(build system)"


def run(platform: str, rows: list[dict], baseline_path: Path, update: bool, hold_only: bool = False) -> int:
    counts = count_kinds(rows)
    baseline = _load_baseline(baseline_path) if baseline_path.is_file() else {}
    if hold_only and platform not in baseline:
        raise Blind(f"no baseline for platform {platform} in {baseline_path}")
    if update or platform not in baseline:
        baseline[platform] = counts
        _write_baseline(baseline_path, baseline)
        print(f"check_xcode_warning_ratchet: {platform}: baseline {'updated' if update else 'set'} -> {sum(counts.values())} warnings, {len(counts)} kinds")
        return 0
    held = baseline[platform]
    grew = {k: (c, int(held.get(k, 0))) for k, c in counts.items() if c > int(held.get(k, 0))}
    if grew:
        for kind, (now, was) in sorted(grew.items()):
            print(f"  {platform}: {kind}: {now} vs baseline {was} -> GREW")
            for r in [r for r in rows if r["kind"] == kind][:20]:
                print(f"      {_at(r)}: {r['message'][:160]}")
        print("\nxcode warning ratchet FAILED: a warning kind grew past its baseline on this platform. Held exactly, per kind: fix "
              "the new warning; a count may only fall.")
        return 1
    fell = {k: (int(v), counts.get(k, 0)) for k, v in held.items() if counts.get(k, 0) < int(v)}
    if fell:
        if not hold_only:
            baseline[platform] = counts
            _write_baseline(baseline_path, baseline)
        for kind, (was, now) in sorted(fell.items()):
            print(f"  {platform}: {kind}: {now} warnings, fewer than {was}: the baseline is lower now")
        return 0
    print(f"check_xcode_warning_ratchet: {platform}: {sum(counts.values())} warnings, {len(counts)} kinds (held): OK")
    return 0


def raised(old: dict, new: dict) -> list[str]:
    """Every (platform, kind) whose count the new baseline raises over the old one, a kind the old never had included."""
    out = []
    for platform, kinds in new.items():
        for kind, count in (kinds or {}).items():
            was = int((old.get(platform) or {}).get(kind, 0))
            if int(count) > was:
                out.append(f"{platform}: {kind}: {was} -> {count}")
    return out


def run_since(platform: str, rows: list[dict], base_rows: list[dict]) -> int:
    """Only this item's new lines: the kinds whose count rose over the base (netting per kind, not per file)."""
    before, after = count_kinds(base_rows), count_kinds(rows)
    seen = Counter((r["kind"], r["file"], r["message"]) for r in base_rows)
    added = 0
    for kind in sorted(after):
        extra = after[kind] - before.get(kind, 0)
        if extra <= 0:
            continue
        added += extra
        mine = [r for r in rows if r["kind"] == kind]
        new = []
        for r in mine:  # a line the base also had (same file and message) is not the item's
            key = (r["kind"], r["file"], r["message"])
            if seen[key] > 0:
                seen[key] -= 1
            else:
                new.append(r)
        print(f"  +{extra}  {platform}: {kind} ({before.get(kind, 0)} -> {after[kind]})")
        for r in (new or mine)[:max(extra, 1)]:
            print(f"      {_at(r)}: {r['message'][:160]}")
    if added:
        print("xcode warning ratchet --since: this item adds warnings")
        return 1
    print(f"xcode warning ratchet --since: nothing added ({sum(before.values())} -> {sum(after.values())})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--platform", default="mac", help="mac, ios or ipad")
    p.add_argument("--bundle", help="a .xcresult folder, or a file holding its build-results JSON")
    p.add_argument("--log", help="the kept build log, read only when there is no bundle")
    p.add_argument("--baseline", type=Path, default=None, help=f"default {DEFAULT_BASELINE}")
    p.add_argument("--update-baseline", action="store_true")
    p.add_argument("--hold-only", action="store_true", help="never write the baseline (the build rung: the land step lowers it); no platform entry is BLIND")
    p.add_argument("--since", metavar="BASE", help="the base build's bundle or JSON: report only this item's new lines")
    p.add_argument("--check-baseline", metavar="NEW", type=Path, help="refuse a baseline that raises a count over --was")
    p.add_argument("--was", type=Path, help="the baseline before the edit, for --check-baseline")
    a = p.parse_args(argv)
    try:
        if a.check_baseline is not None:
            if a.was is None:
                raise Blind("--check-baseline needs --was <old baseline>")
            bad = raised(_load_baseline(a.was), _load_baseline(a.check_baseline))
            for line in bad:
                print(f"  raised: {line}")
            if bad:
                print("xcode warning baseline REFUSED: a baseline may only be lowered")
            return 1 if bad else 0
        if not a.bundle and not a.log and a.since is None and not a.update_baseline:
            # the guards rung runs every check_*.py before any build: no bundle was named, so there is nothing to read, and that is not red
            print("check_xcode_warning_ratchet: skipped: no build to read")
            return 0
        rows = read_warnings(a.bundle, a.log, a.platform)
        if a.since is not None:
            return run_since(a.platform, rows, read_warnings(a.since, None, a.platform))
        path = a.baseline if a.baseline is not None else DEFAULT_BASELINE
        if a.baseline is None and not a.update_baseline and not path.is_file():
            raise Blind(f"baseline missing at {path} (the tree moved; restore it from git)")
        return run(a.platform, rows, path, a.update_baseline, a.hold_only)
    except Blind as exc:
        print(f"check_xcode_warning_ratchet: BLIND — {exc}", file=sys.stderr)
        return BLIND_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
