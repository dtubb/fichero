#!/usr/bin/env python3
"""An app feature is done only when its screen exists (#7067).

The Models & Cluster window's stages landed as engine answers and pure rules with no window and were reported done.
Two rules, both shrink-only against scripts/check_spec_app_evidence_baseline.json:

  1. engine_only: a spec behaviour tagged [OK] or [BUILT] whose text after the tag names the `app` must cite a Swift test
     (fichero/Tests/...swift, a UI test included). Citing only pytest files is "engine done, the app part is not".
  2. no_ux_section: a spec file with app behaviours (any live tag whose text names the `app`) must have a "What the person
     sees" (or "UX") section that names where the person opens it, the empty, loading and error states, and an
     acceptance line.

A new offender fails. A baselined entry that now passes and is still listed also fails, so the list can only shrink.

    python scripts/check_spec_app_evidence.py
    python scripts/check_spec_app_evidence.py --update-baseline   # rewrites the baseline from the specs (shrinks it; refuses to grow it)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "scripts/check_spec_app_evidence_baseline.json"
SPECS = pathlib.Path("docs/contributor_manual/specs")

# One definition of "a behaviour line and its block", shared with the sibling guards.
_SRC = REPO_ROOT / "scripts/check_spec_broken_has_issue.py"
_MOD = importlib.util.spec_from_file_location("_spec_broken", _SRC)
assert _MOD and _MOD.loader
_broken = importlib.util.module_from_spec(_MOD)
sys.modules[_MOD.name] = _broken
_MOD.loader.exec_module(_broken)

TAG_RE = re.compile(r"\*{0,2}\[(OK|BUILT|BROKEN|GAP(?:/BROKEN)?|PARTIAL|MISSING)[^\]]*\]\*{0,2}")
APP_RE = re.compile(r"\bapp\b", re.IGNORECASE)
SWIFT_TEST_RE = re.compile(r"fichero/Tests/[\w./-]+\.swift|\b\w*UITests?\w*\.swift")
HEADING_RE = re.compile(r"^(#+)\s+(.*)$")
UX_HEADING_RE = re.compile(r"what the person sees|\bUX\b", re.IGNORECASE)
UX_NEEDS = {
    "opener": re.compile(r"\b(menu|window|pane|shortcut|toolbar|sidebar|opens?|opened)\b", re.IGNORECASE),
    "empty": re.compile(r"\bempty\b", re.IGNORECASE),
    "loading": re.compile(r"\bloading\b", re.IGNORECASE),
    "error": re.compile(r"\berror\b", re.IGNORECASE),
    "acceptance": re.compile(r"\bacceptance\b", re.IGNORECASE),
}


def _spec_files(root: pathlib.Path) -> list[pathlib.Path]:
    specs = root / SPECS
    out = []
    for p in sorted(specs.rglob("*.md")):
        rel = p.relative_to(specs)
        if p.name.startswith("_") or any(part.startswith(".") for part in rel.parts):
            continue
        out.append(p)
    return out


def behaviours(root: pathlib.Path):
    """Yield (relative spec path, behaviour id, tag, text after the tag) for every tagged behaviour."""
    for p in _spec_files(root):
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(root).as_posix()
        for _line, bid, block in _broken._iter_behavior_blocks(text.splitlines()):
            m = TAG_RE.search(block)
            if m:
                yield rel, bid, m.group(1), block[m.end():]


def engine_only_offenders(root: pathlib.Path) -> set[str]:
    return {
        f"{rel}::{bid}"
        for rel, bid, tag, scope in behaviours(root)
        if tag in ("OK", "BUILT") and APP_RE.search(scope) and not SWIFT_TEST_RE.search(scope)
    }


def ux_section(text: str) -> str | None:
    """The body of the first UX heading, up to the next heading of the same or a higher level."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and UX_HEADING_RE.search(m.group(2)):
            body = []
            for nxt in lines[i + 1:]:
                h = HEADING_RE.match(nxt)
                if h and len(h.group(1)) <= len(m.group(1)):
                    break
                body.append(nxt)
            return "\n".join(body)
    return None


def ux_problems(text: str) -> list[str]:
    """What a spec's UX section lacks; a missing section lacks everything."""
    section = ux_section(text)
    if section is None:
        return list(UX_NEEDS)
    return [name for name, rx in UX_NEEDS.items() if not rx.search(section)]


def app_specs(root: pathlib.Path) -> set[str]:
    return {rel for rel, _bid, _tag, scope in behaviours(root) if APP_RE.search(scope)}


def no_ux_specs(root: pathlib.Path) -> set[str]:
    return {rel for rel in app_specs(root) if ux_problems((root / rel).read_text(encoding="utf-8"))}


def current(root: pathlib.Path) -> dict[str, set[str]]:
    return {"engine_only": engine_only_offenders(root), "no_ux_section": no_ux_specs(root)}


def judge(root: pathlib.Path, baseline: pathlib.Path) -> tuple[list[str], list[str]]:
    """(new offenders, baselined entries that now pass), each as `<rule>: <key>`."""
    listed = json.loads(baseline.read_text(encoding="utf-8"))
    now = current(root)
    new, stale = [], []
    for rule, found in now.items():
        have = set(listed.get(rule, []))
        new += [f"{rule}: {k}" for k in sorted(found - have)]
        stale += [f"{rule}: {k}" for k in sorted(have - found)]
    return new, stale


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()
    if not (REPO_ROOT / SPECS).exists():
        print(f"FAIL check_spec_app_evidence: no specs at {REPO_ROOT / SPECS} (blind, not green)")
        return 2
    if args.update_baseline:
        now = current(REPO_ROOT)
        old = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None
        if old is not None:
            grown = [f"{r}: {k}" for r, found in now.items() for k in sorted(found - set(old.get(r, [])))]
            if grown:
                print("REFUSED: the baseline may only shrink; fix these instead:\n  " + "\n  ".join(grown))
                return 1
        BASELINE.write_text(json.dumps({r: sorted(v) for r, v in now.items()}, indent=1) + "\n", encoding="utf-8")
        print("baseline written: " + ", ".join(f"{r} {len(v)}" for r, v in now.items()))
        return 0
    new, stale = judge(REPO_ROOT, BASELINE)
    if new:
        print("FAIL check_spec_app_evidence: engine done, the app part is not (cite a Swift test; give the spec a "
              "'What the person sees' section with opener, empty/loading/error states and an acceptance line):")
        print("  " + "\n  ".join(new))
    if stale:
        print("FAIL check_spec_app_evidence: these baselined entries now pass; remove them from "
              "scripts/check_spec_app_evidence_baseline.json:")
        print("  " + "\n  ".join(stale))
    if new or stale:
        return 1
    print("check_spec_app_evidence: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
