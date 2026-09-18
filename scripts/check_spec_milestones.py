#!/usr/bin/env python3
"""Every APPROVED design-led spec is tracked by a GitHub milestone of the SAME name.

The rule (creative-director, 2026-09-09): spec name == milestone name, so a feature's
design (the spec), its issues (the milestone), and its tests (the tag/marker) all share one
identifier. This is bidirectional — the milestone's description points back at the spec.

Enforcement is split so the gate stays deterministic OFFLINE:
  * HARD (this guardrail, offline): an APPROVED spec MUST declare `Milestone: <name>` in its
    header. That is the contract the gate owns.
  * SOFT (only when `gh` is available AND online): the declared milestone should actually exist
    on GitHub. A missing milestone prints a warning here but does NOT fail the gate — creating /
    renaming the milestone is done as the spec is written, not blocked by network in CI.

Run: python scripts/check_spec_milestones.py
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")
MILESTONE_RE = re.compile(r"Milestone:\s*(\S+)")

# Specs approved BEFORE the milestone-declaration rule (2026-09-09). They graduate off this
# list by gaining a `Milestone:` header as their area is next worked — "sorted over time"
# (creative-director). Do NOT add new specs here; new APPROVED specs must declare a milestone.
MILESTONE_GRANDFATHERED = {
    "workflow-node-config",
}


def _is_scaffold(p: pathlib.Path) -> bool:
    return p.name.startswith("_")


def _approved_specs() -> list[pathlib.Path]:
    out = []
    for p in SPECS_DIR.rglob("*.md"):
        if _is_scaffold(p):
            continue
        head = p.read_text(encoding="utf-8")[:800]
        if re.search(r"Status:\s*APPROVED", head):
            out.append(p)
    return out


def _declared_milestone(spec: pathlib.Path) -> str | None:
    m = MILESTONE_RE.search(spec.read_text(encoding="utf-8")[:800])
    return m.group(1) if m else None


def _live_milestones() -> set[str] | None:
    """GitHub milestone titles, or None when gh/network is unavailable (soft-skip)."""
    if shutil.which("gh") is None:
        return None
    try:
        proc = subprocess.run(
            ["gh", "api", "repos/:owner/:repo/milestones", "--paginate",
             "-q", ".[].title"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def main() -> int:
    if not SPECS_DIR.exists():
        print(f"FAIL: specs directory missing: {SPECS_DIR}")
        return 1

    approved = _approved_specs()
    hard_failures: list[str] = []
    declared: dict[str, str] = {}
    for spec in approved:
        name = _declared_milestone(spec)
        if name is None and spec.stem in MILESTONE_GRANDFATHERED:
            continue
        if name is None:
            hard_failures.append(
                f"{spec.relative_to(SPECS_DIR)}: APPROVED spec must declare "
                f"`Milestone: <name>` in its header (spec name == milestone name)."
            )
        else:
            declared[spec.stem] = name

    # Soft, best-effort: does each declared milestone actually exist?
    live = _live_milestones()
    if live is not None:
        for stem, name in sorted(declared.items()):
            if name not in live:
                print(
                    f"WARN {stem}: declared Milestone '{name}' not found on GitHub — "
                    f"create or rename it (not a hard gate)."
                )

    if hard_failures:
        print("FAIL check_spec_milestones:")
        for f in hard_failures:
            print(f"  - {f}")
        return 1
    print(
        f"OK check_spec_milestones: {len(approved)} approved specs, all declare a milestone"
        + ("" if live is None else "; existence checked against GitHub")
        + "."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
